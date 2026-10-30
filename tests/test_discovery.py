import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.discovery.cost import CostRates, estimate_cost
from backend.discovery.models import DiscoveredCandidate, ResearchResult, SelectionResult, UsageRecord
from backend.discovery.normalize import canonicalize_url, domain_matches, known_source_ids
from backend.discovery.openai_provider import OpenAIProvider
from backend.discovery.openrouter_provider import OpenRouterProvider, discovery_model
from backend.discovery.query import limit_from_query, resolve_limit
from backend.discovery.registry import load_registry, sync_registry
from backend.discovery.runner import run_discovery_job
from backend.discovery.search import grounded_candidates, search_links_from_response
from backend.models import (
    DiscoveryUsage,
    FundingProgram,
    FundingSource,
    FundingType,
    IngestionJob,
    JobStatus,
    OpportunityCandidate,
    ReviewStatus,
    SourceKind,
)

REGISTRY = Path(__file__).resolve().parents[1] / "configs" / "sources.yaml"


def test_normalization_and_shared_domain_matching():
    registry = load_registry(REGISTRY)
    assert canonicalize_url("http://Example.COM/grants/?utm_source=google&year=2026#apply") == "https://example.com/grants?year=2026"
    assert domain_matches("https://www.canada.ca/en/", "canada.ca")
    assert not domain_matches("https://canada.ca.evil.org/a", "canada.ca")
    url = "https://www.canada.ca/en/women-gender-equality/funding/some-call.html"
    assert known_source_ids(url, registry) == ["wage"]


def test_only_observed_links_can_become_candidates():
    payload = {"output": [
        {"type": "web_search_call", "action": {"sources": [{"url": "https://example.org/grant?utm_source=x"}]}},
        {"type": "message", "content": [{"annotations": [{"url": "https://example.org/loan"}],
            "text": "ignore this fake link https://example.org/hallucinated"}]},
    ]}
    observed = search_links_from_response(payload)
    assert observed == {"https://example.org/grant", "https://example.org/loan"}
    selected = [
        DiscoveredCandidate(title="Grant", url="https://example.org/grant", provider_hint=None, type_hint="grant", reason_to_investigate="Relevant"),
        DiscoveredCandidate(title="Fake", url="https://example.org/hallucinated", provider_hint=None, type_hint="grant", reason_to_investigate="Unsupported"),
    ]
    assert [item.title for item in grounded_candidates(selected, observed, ["example.org"], 8)] == ["Grant"]


def test_cost_estimate_uses_configured_rates():
    usage = UsageRecord(operation="research", response_id="resp_1", model="test-model", input_tokens=1000,
                        cached_input_tokens=200, cache_write_tokens=100, output_tokens=500, web_search_calls=2)
    rates = CostRates(input_per_million=Decimal(1), cached_input_per_million=Decimal("0.1"),
                      cache_write_per_million=Decimal("1.25"), output_per_million=Decimal(4),
                      web_search_per_call=Decimal("0.01"))
    assert estimate_cost(usage, rates) == Decimal("0.022845")


def test_openai_adapter_records_usage_without_live_request():
    class Response:
        id = "resp_fake"
        output_text = "Found one page"
        output_parsed = SimpleNamespace(candidates=[DiscoveredCandidate(
            title="Grant", url="https://example.org/grant", provider_hint=None,
            type_hint="grant", reason_to_investigate="Relevant",
        )])

        def model_dump(self, exclude_none=True):
            return {"id": self.id, "model": "test-model", "usage": {
                "input_tokens": 120, "output_tokens": 40,
                "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 0},
            }, "output": [{"type": "web_search_call", "action": {
                "type": "search", "sources": [{"url": "https://example.org/grant"}],
            }}]}

    class Responses:
        def create(self, **kwargs):
            self.create_args = kwargs
            return Response()

        def parse(self, **kwargs):
            self.parse_args = kwargs
            return Response()

    responses = Responses()
    provider = OpenAIProvider(client=SimpleNamespace(responses=responses))
    research = provider.research("grant", "test-model", ["example.org"], 8)
    assert responses.create_args["tools"][0]["filters"]["allowed_domains"] == ["example.org"]
    assert research.usage.input_tokens == 120
    assert research.usage.cached_input_tokens == 20
    assert research.usage.web_search_calls == 1
    selection = provider.select("grant", {"https://example.org/grant"}, "Found one page", "test-model", 8)
    assert selection.candidates[0].title == "Grant"
    assert responses.parse_args["text_format"].__name__ == "DiscoveryBatch"


class FakeProvider:
    def research(self, query, model, allowed_domains, limit, search_context_size="medium"):
        response_id = f"resp_{uuid4().hex}"
        return ResearchResult(response_id=response_id, model=model, summary="Found one page", payload={"output": [
            {"type": "web_search_call", "action": {"type": "search", "sources": [{"url": "https://www.canada.ca/en/women-gender-equality/funding/call.html"}]}}
        ]}, usage=UsageRecord(operation="research", response_id=response_id, model=model, input_tokens=100,
                              output_tokens=50, web_search_calls=1))

    def select(self, query, observed_urls, research_summary, model, limit):
        response_id = f"resp_{uuid4().hex}"
        return SelectionResult(response_id=response_id, candidates=[DiscoveredCandidate(
            title="Community grant", url="https://www.canada.ca/en/women-gender-equality/funding/call.html",
            provider_hint="WAGE", type_hint="grant", reason_to_investigate="Potential fit")],
            usage=UsageRecord(operation="selection", response_id=response_id, model=model, input_tokens=80,
                              output_tokens=30, web_search_calls=0))


def test_worker_stages_idempotently_and_records_each_paid_call(db_engine):
    rates = CostRates(input_per_million=Decimal(1), cached_input_per_million=Decimal(1),
                      cache_write_per_million=Decimal(1), output_per_million=Decimal(1),
                      web_search_per_call=Decimal("0.01"))
    with Session(db_engine) as db:
        sources = sync_registry(db, load_registry(REGISTRY))
        wage = sources["wage"]
        jobs = [IngestionJob(source_id=wage.id, job_metadata={"mode": "trusted", "query": "community funding", "limit": 8}) for _ in range(2)]
        db.add_all(jobs)
        db.commit()
        for job in jobs:
            run_discovery_job(db, job.id, FakeProvider(), "test-model", rates)
        candidates = db.scalars(select(OpportunityCandidate)).all()
        assert len(candidates) == 1
        assert candidates[0].status == "unverified"
        assert candidates[0].source_id == wage.id
        assert candidates[0].program_id is None
        assert len(db.scalars(select(DiscoveryUsage)).all()) == 4
        assert all(job.status == JobStatus.succeeded for job in jobs)
        assert db.scalars(select(FundingProgram)).all() == []


def test_failed_selection_keeps_research_usage(db_engine):
    class FailingProvider(FakeProvider):
        def select(self, *args, **kwargs):
            raise RuntimeError("selection failed")

    with Session(db_engine) as db:
        source = sync_registry(db, load_registry(REGISTRY))["wage"]
        job = IngestionJob(source_id=source.id, job_metadata={"mode": "trusted", "query": "grant", "limit": 8})
        db.add(job)
        db.commit()
        with pytest.raises(RuntimeError, match="selection failed"):
            run_discovery_job(db, job.id, FailingProvider(), "test-model", None)
        assert db.get(IngestionJob, job.id).status == JobStatus.failed
        assert len(db.scalars(select(DiscoveryUsage)).all()) == 1


def test_trusted_manual_source_uses_its_hostname(db_engine):
    with Session(db_engine) as db:
        source = FundingSource(name="Manual government source", base_url="https://www.canada.ca/en/funding", kind=SourceKind.website)
        db.add(source)
        db.commit()
        job = IngestionJob(source_id=source.id, job_metadata={"mode": "trusted", "query": "grant", "limit": 8})
        db.add(job)
        db.commit()
        staged = run_discovery_job(db, job.id, FakeProvider(), "test-model", None)
        assert len(staged) == 1
        assert staged[0].source_id == source.id


def test_candidate_api_promotes_only_after_human_action(client, db_engine):
    with Session(db_engine) as db:
        source = sync_registry(db, load_registry(REGISTRY))["wage"]
        candidate = OpportunityCandidate(source_id=source.id, url="https://example.org/grant",
            canonical_url="https://example.org/grant", title="Grant", status="unverified",
            extracted_data={"reason_to_investigate": "Possible fit", "summary": "Supports community groups.", "geography": "Canada"})
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id
    assert client.get("/candidates").json()[0]["id"] == str(candidate_id)
    promoted = client.post(f"/candidates/{candidate_id}/promote", json={"funding_type": "grant"})
    assert promoted.status_code == 200
    assert promoted.json()["status"] == "promoted"
    assert promoted.json()["program_id"]
    assert client.get("/review-queue").json()[0]["program_id"] == promoted.json()["program_id"]
    assert client.post(f"/candidates/{candidate_id}/promote", json={"funding_type": "grant"}).status_code == 409
    program = client.get(f"/opportunities/{promoted.json()['program_id']}")
    assert program.json()["summary"] == "Supports community groups."
    assert program.json()["geography"] == "Canada"


def test_usage_summary_exposes_measured_usage_and_unknown_cost(client, db_engine):
    with Session(db_engine) as db:
        source = sync_registry(db, load_registry(REGISTRY))["wage"]
        job = IngestionJob(source_id=source.id, job_metadata={"mode": "trusted", "query": "grant", "limit": 8})
        db.add(job)
        db.commit()
        run_discovery_job(db, job.id, FakeProvider(), "test-model", None)
        job_id = str(job.id)
    summary = client.get("/discovery/usage-summary").json()
    assert summary["input_tokens"] == 180
    assert summary["output_tokens"] == 80
    assert summary["web_search_calls"] == 1
    assert summary["estimated_cost_usd"] is None
    events = client.get("/discovery/usage").json()
    assert len(events) == 2
    assert {event["operation"] for event in events} == {"research", "selection"}
    assert all(event["job_id"] == job_id for event in events)


def test_openrouter_provider_uses_the_enrichment_model_and_cited_pages(monkeypatch):
    monkeypatch.setenv("BRIDGE_ENRICHMENT_MODEL", "google/gemini-2.5-flash-lite")
    calls = []
    dumps = json.dumps

    class Client:
        def post(self, url, headers, json):
            calls.append(json)
            if len(calls) == 1:
                return httpx.Response(200, json={
                    "id": "resp_research", "model": json["model"],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 4, "cost": "0.001",
                              "server_tool_use": {"web_search_requests": 1}},
                    "choices": [{"message": {
                        "content": "One program page. Ignore https://example.org/hallucinated",
                        "annotations": [{"type": "url_citation", "url_citation": {
                            "url": "https://example.org/grant", "title": "Grant",
                        }}],
                    }}],
                })
            return httpx.Response(200, json={
                "id": "resp_select", "model": json["model"],
                "usage": {"prompt_tokens": 8, "completion_tokens": 6, "cost": "0.0004"},
                "choices": [{"message": {"content": dumps({
                    "candidates": [{
                        "title": "Grant", "url": "https://example.org/grant", "provider_hint": None,
                        "type_hint": "grant", "reason_to_investigate": "Cited page",
                        "summary": "Supports community groups.", "geography": "Canada", "audience": "Women",
                    }],
                })}}],
            })

    assert discovery_model() == "google/gemini-2.5-flash-lite"
    provider = OpenRouterProvider(client=Client())
    research = provider.research("find 5 grants", discovery_model(), ["example.org"], 5, "low")
    assert calls[0]["model"] == "google/gemini-2.5-flash-lite"
    assert calls[0]["tools"][0]["type"] == "openrouter:web_search"
    assert calls[0]["tools"][0]["parameters"]["allowed_domains"] == ["example.org"]
    assert calls[0]["tools"][0]["parameters"]["search_context_size"] == "low"
    assert search_links_from_response(research.payload) == {"https://example.org/grant"}
    assert research.usage.provider == "openrouter"
    assert research.usage.reported_cost_usd == Decimal("0.001")
    selection = provider.select("find 5 grants", {"https://example.org/grant"}, research.summary, discovery_model(), 5)
    assert selection.candidates[0].summary == "Supports community groups."
    assert calls[1]["response_format"]["type"] == "json_schema"


def test_cited_page_is_saved_when_selection_is_empty(db_engine):
    class CiteOnly(FakeProvider):
        def select(self, query, observed_urls, research_summary, model, limit):
            response_id = f"resp_{uuid4().hex}"
            return SelectionResult(
                response_id=response_id, candidates=[],
                usage=UsageRecord(operation="selection", response_id=response_id, model=model, input_tokens=4, output_tokens=2),
            )

        def research(self, query, model, allowed_domains, limit, search_context_size="medium"):
            response_id = f"resp_{uuid4().hex}"
            return ResearchResult(
                response_id=response_id, model=model, summary="Cited one page",
                payload={"output": [{"type": "web_search_call", "action": {"type": "search", "sources": [
                    {"url": "https://example.org/women-fund", "title": "Women Founders Fund"},
                ]}}]},
                usage=UsageRecord(operation="research", response_id=response_id, model=model, input_tokens=5,
                                  output_tokens=3, web_search_calls=1),
            )

    with Session(db_engine) as db:
        job = IngestionJob(job_metadata={
            "mode": "open", "query": "find 1 more opportunity in Canada that is women-focused",
            "limit": 1, "depth": "superficial", "kind": "query_discovery",
        })
        db.add(job)
        db.commit()
        staged = run_discovery_job(db, job.id, CiteOnly(), "test-model", None)
        assert staged[0].canonical_url == "https://example.org/women-fund"
        assert staged[0].title == "Women Founders Fund"


def test_query_limit_reads_a_plain_language_request():
    query = "find 5 more opportunities in Canada that are women-focused"
    assert limit_from_query(query) == 5
    assert limit_from_query("Find five grants for women in Canada") == 5
    assert limit_from_query("8 more community funds") == 8
    assert limit_from_query("women-focused funding") is None
    assert resolve_limit("women-focused funding", None) == 5
    assert resolve_limit(query, 2) == 2
    assert limit_from_query("find 40 opportunities") == 30


def test_discovery_skips_known_pages_and_titles(db_engine):
    class MixedProvider:
        def research(self, query, model, allowed_domains, limit, search_context_size="medium"):
            self.query = query
            self.context = search_context_size
            response_id = f"resp_{uuid4().hex}"
            urls = [
                "https://example.org/existing-grant",
                "https://example.org/funding",
                "https://example.org/same-name",
                "https://example.org/new-grant",
            ]
            return ResearchResult(
                response_id=response_id, model=model, summary="Four pages",
                payload={"output": [{"type": "web_search_call", "action": {"type": "search", "sources": [{"url": url} for url in urls]}}]},
                usage=UsageRecord(operation="research", response_id=response_id, model=model, input_tokens=10, output_tokens=5, web_search_calls=1),
            )

        def select(self, query, observed_urls, research_summary, model, limit):
            response_id = f"resp_{uuid4().hex}"
            rows = [
                ("Existing Women Grant", "https://example.org/existing-grant", None, None, None),
                ("Example portal", "https://example.org/funding", None, None, None),
                ("Existing Women Grant", "https://example.org/same-name", None, None, None),
                ("Prairie Women Founders Fund", "https://example.org/new-grant", "Supports women founders.", "Canada", "Women"),
            ]
            return SelectionResult(
                response_id=response_id,
                candidates=[DiscoveredCandidate(
                    title=title, url=url, provider_hint=None, type_hint="grant", reason_to_investigate="Search result",
                    summary=summary, geography=geography, audience=audience,
                ) for title, url, summary, geography, audience in rows],
                usage=UsageRecord(operation="selection", response_id=response_id, model=model, input_tokens=8, output_tokens=4),
            )

    provider = MixedProvider()
    with Session(db_engine) as db:
        db.add(FundingSource(name="Example portal", base_url="https://example.org/funding", kind=SourceKind.website))
        db.add(FundingProgram(
            title="Existing Women Grant", funding_type=FundingType.grant, url="https://www.example.org/existing-grant",
            review_status=ReviewStatus.pending, organization_types=[],
        ))
        job = IngestionJob(job_metadata={
            "mode": "open", "query": "find 5 more opportunities in Canada that are women-focused",
            "limit": 5, "depth": "superficial", "kind": "query_discovery",
        })
        db.add(job)
        db.commit()
        staged = run_discovery_job(db, job.id, provider, "test-model", None)
        assert [item.canonical_url for item in staged] == ["https://example.org/new-grant"]
        assert staged[0].extracted_data["summary"] == "Supports women founders."
        assert staged[0].extracted_data["geography"] == "Canada"
        assert staged[0].extracted_data["audience"] == "Women"
        assert staged[0].status == "unverified"
        saved = db.get(IngestionJob, job.id)
        assert saved.job_metadata["candidates_created"] == 1
        assert saved.job_metadata["duplicates_skipped"] == 3
        assert {item["match"] for item in saved.job_metadata["skipped"]} == {"url", "title"}
        assert "Existing Women Grant" in provider.query
        assert "Stay superficial" in provider.query
        assert provider.context == "low"


def test_admin_discovery_run_executes_and_parses_the_requested_count(client, monkeypatch):
    monkeypatch.setattr("backend.discovery.runs.configuration_error", lambda: None)
    monkeypatch.setattr("backend.discovery.runs.provider_for_run", lambda: (FakeProvider(), "test-model", None))
    response = client.post("/api/admin/discovery-runs", json={
        "query": "find 5 more opportunities in Canada that are women-focused",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["job_metadata"]["kind"] == "query_discovery"
    assert body["job_metadata"]["depth"] == "superficial"
    assert body["job_metadata"]["limit"] == 5
    assert body["job_metadata"]["candidates_created"] == 1
    leads = client.get("/candidates?status=unverified").json()
    assert leads[0]["canonical_url"].startswith("https://")
    assert client.post("/api/admin/discovery-runs", json={"query": "find grants"}, headers={"X-Admin-Key": "nope"}).status_code == 401


def test_admin_discovery_run_does_not_call_the_provider_without_configuration(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def forbid():
        raise AssertionError("provider should not be built")

    monkeypatch.setattr("backend.discovery.runs.provider_for_run", forbid)
    response = client.post("/api/admin/discovery-runs", json={"query": "find 5 grants for women in Canada"})
    assert response.status_code == 201
    assert response.json()["status"] == "failed"
    assert "OPENROUTER_API_KEY" in response.json()["error"]


def test_admin_discovery_run_rejects_a_second_active_search(client, db_engine):
    with Session(db_engine) as db:
        db.add(IngestionJob(job_metadata={"kind": "query_discovery", "mode": "open", "query": "find grants", "limit": 5}))
        db.commit()
    response = client.post("/api/admin/discovery-runs", json={"query": "find 5 grants for women in Canada"})
    assert response.status_code == 409


def test_stuck_discovery_run_does_not_block_the_next_search(client, db_engine, monkeypatch):
    monkeypatch.setattr("backend.discovery.runs.configuration_error", lambda: None)
    monkeypatch.setattr("backend.discovery.runs.provider_for_run", lambda: (FakeProvider(), "test-model", None))
    with Session(db_engine) as db:
        old = IngestionJob(
            status=JobStatus.running, started_at=datetime.now(UTC) - timedelta(minutes=11),
            job_metadata={"kind": "query_discovery", "mode": "open", "query": "old", "limit": 5},
        )
        db.add(old)
        db.commit()
        old_id = old.id
    response = client.post("/api/admin/discovery-runs", json={"query": "find 5 more opportunities in Canada that are women-focused"})
    assert response.status_code == 201
    assert response.json()["status"] == "succeeded"
    with Session(db_engine) as db:
        assert db.get(IngestionJob, old_id).status == JobStatus.failed
