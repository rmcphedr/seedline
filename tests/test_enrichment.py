import io
import sys
import types
import urllib.request
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import yaml
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import enrichment
from backend import models as m
from backend.windmill import WindmillClient


def program(client):
    source = client.post(
        "/sources", json={"name": "Fund", "base_url": "https://fund.example", "kind": "website"}
    ).json()
    return client.post(
        "/opportunities",
        json={
            "source_id": source["id"],
            "title": "Original",
            "funding_type": "grant",
            "url": "https://fund.example/grant",
            "summary": "Verified text",
        },
    ).json()


def test_windmill_client_sends_ids_and_reads_job_uuid(monkeypatch):
    calls = []
    job_id = uuid4()

    def handle(request):
        calls.append(request)
        return httpx.Response(201, json=str(job_id))

    client = WindmillClient("http://windmill:8000", "bridge", "f/bridge/enrich_funding_opportunity", "token")
    client.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    opportunity_id, enrichment_job_id = uuid4(), uuid4()
    import asyncio

    assert asyncio.run(client.trigger(opportunity_id, enrichment_job_id)) == job_id
    assert calls[0].url.path == "/api/w/bridge/jobs/run/f/f/bridge/enrich_funding_opportunity"
    assert calls[0].headers["Authorization"] == "Bearer token"
    assert calls[0].read().decode() == (
        f'{{"opportunity_id":"{opportunity_id}","enrichment_job_id":"{enrichment_job_id}"}}'
    )
    asyncio.run(client.http_client.aclose())


def test_windmill_client_accepts_plain_uuid_response():
    job_id = uuid4()
    client = WindmillClient("http://windmill:8000", "bridge", "f/bridge/enrich_funding_opportunity", "token")
    client.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(201, text=str(job_id)))
    )
    import asyncio

    assert asyncio.run(client.trigger(uuid4(), uuid4())) == job_id
    asyncio.run(client.http_client.aclose())


def test_admin_trigger_duplicate_and_worker_lifecycle(client, db_engine, monkeypatch):
    item = program(client)
    review = client.get("/review-queue").json()[0]
    assert client.post(f"/review-queue/{review['id']}/approve", json={}).status_code == 200
    assert client.post(f"/opportunities/{item['id']}/publish").status_code == 200
    windmill_id = uuid4()
    calls = []

    async def trigger(self, opportunity_id, enrichment_job_id):
        calls.append((opportunity_id, enrichment_job_id))
        return windmill_id

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    monkeypatch.setenv("WINDMILL_URL", "http://windmill:8000")
    monkeypatch.setenv("WINDMILL_WORKSPACE", "bridge")
    monkeypatch.setenv("WINDMILL_FLOW_PATH", "f/bridge/enrich_funding_opportunity")
    monkeypatch.setenv("WINDMILL_API_TOKEN", "token")
    monkeypatch.setenv("BRIDGE_WORKER_API_KEY", "worker-secret")
    path = "/api/admin/enrichment-jobs"
    assert client.post(path, json={"opportunity_ids": [item["id"]]}, headers={"X-Admin-Key": "bad"}).status_code == 401
    created = client.post(path, json={"opportunity_ids": [item["id"]]})
    assert created.status_code == 201
    job = created.json()[0]
    assert calls == [(UUID(item["id"]), UUID(job["id"]))]
    assert job["windmill_job_id"] == str(windmill_id)
    assert client.post(path, json={"opportunity_ids": [item["id"]]}).status_code == 409
    assert client.get(f"{path}/{job['id']}").json()["status"] == "queued"

    worker = {"X-Worker-Key": "worker-secret"}
    base = f"/api/internal/enrichment-jobs/{job['id']}"
    assert client.get(f"{base}/load").status_code == 401
    loaded = client.get(f"{base}/load?opportunity_id={item['id']}", headers=worker)
    assert loaded.status_code == 200
    assert loaded.json()["url"] == item["url"]
    assert client.get(f"{base}/load?opportunity_id={uuid4()}", headers=worker).status_code == 409

    def fake_fetch(url):
        return "<h1>Updated</h1><p>New funding details</p>"

    monkeypatch.setattr(enrichment, "fetch_source", fake_fetch)
    fetched = client.post(f"{base}/fetch", headers=worker)
    assert fetched.status_code == 200
    assert fetched.json()["content_hash"]

    def fake_extract(text, url):
        return {"title": "Updated", "summary": "New funding details", "source_url": url}, {
            "model": "test",
            "total_tokens": 5,
        }

    monkeypatch.setattr(enrichment, "extract_fields", fake_extract)
    assert client.post(f"{base}/extract", headers=worker).status_code == 200
    validated = client.post(f"{base}/validate", headers=worker)
    assert validated.status_code == 200
    assert "title" in validated.json()["conflicts"]
    staged = client.post(f"{base}/stage", headers=worker)
    assert staged.status_code == 200
    assert staged.json()["status"] == "succeeded"
    assert staged.json()["display_status"] == "pending_review"
    assert staged.json()["proposed_updates"]["title"] == "Updated"
    saved = client.get(f"/opportunities/{item['id']}").json()
    assert saved["title"] == "Original"
    assert saved["summary"] == "Verified text"
    assert saved["review_status"] == "approved"
    assert saved["publication_status"] == "published"
    assert client.post(f"{path}/{job['id']}/approve", json={"accepted_fields": ["title", "summary"],
                      "edited_fields": {"summary": "Edited summary"}}, headers={"X-Admin-Key": "bad"}).status_code == 401
    accepted = client.post(f"{path}/{job['id']}/approve", json={"accepted_fields": ["title", "summary"],
                           "edited_fields": {"summary": "Edited summary"}})
    assert accepted.status_code == 200
    assert accepted.json()["review_decision"] == "approved"
    saved = client.get(f"/opportunities/{item['id']}").json()
    assert saved["title"] == "Updated"
    assert saved["summary"] == "Edited summary"
    assert saved["review_status"] == "pending"
    assert saved["publication_status"] == "unpublished"
    assert client.post(f"{path}/{job['id']}/approve", json={"accepted_fields": ["title"]}).status_code == 409
    assert client.get(f"/public/opportunities/{item['id']}").status_code == 404
    assert client.post(f"/review-queue/{review['id']}/approve", json={}).status_code == 200
    assert client.post(f"/opportunities/{item['id']}/publish").status_code == 200
    assert client.get(f"/public/opportunities/{item['id']}").json()["summary"] == "Edited summary"
    with Session(db_engine) as db:
        document = db.scalar(select(m.SourceDocument))
        assert document.content_hash == fetched.json()["content_hash"]
        assert db.scalar(select(m.EnrichmentUsage)).total_tokens == 5


def test_failed_dispatch_is_persisted_and_retryable(client, monkeypatch):
    item = program(client)
    monkeypatch.setenv("WINDMILL_URL", "http://windmill:8000")
    monkeypatch.setenv("WINDMILL_WORKSPACE", "bridge")
    monkeypatch.setenv("WINDMILL_FLOW_PATH", "f/bridge/enrich_funding_opportunity")
    monkeypatch.setenv("WINDMILL_API_TOKEN", "token")

    async def fail(self, *_args):
        raise RuntimeError("Windmill unavailable")

    monkeypatch.setattr(WindmillClient, "trigger", fail)
    created = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]})
    assert created.status_code == 201
    failed = created.json()[0]
    assert failed["status"] == "failed"
    assert "Windmill unavailable" in failed["error"]

    async def succeed(self, *_args):
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", succeed)
    retried = client.post(f"/api/admin/enrichment-jobs/{failed['id']}/retry")
    assert retried.status_code == 201
    assert retried.json()["retry_of_id"] == failed["id"]
    assert retried.json()["status"] == "queued"


def test_worker_cannot_publish_and_failure_is_inspectable(client, monkeypatch):
    item = program(client)
    monkeypatch.setenv("WINDMILL_URL", "http://windmill:8000")
    monkeypatch.setenv("WINDMILL_WORKSPACE", "bridge")
    monkeypatch.setenv("WINDMILL_FLOW_PATH", "f/bridge/enrich_funding_opportunity")
    monkeypatch.setenv("WINDMILL_API_TOKEN", "token")
    monkeypatch.setenv("BRIDGE_WORKER_API_KEY", "worker-secret")

    async def trigger(self, *_args):
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    job = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    worker = {"X-Worker-Key": "worker-secret"}
    assert (
        client.post(f"/opportunities/{item['id']}/publish", headers={**worker, "X-Admin-Key": "bad"}).status_code == 401
    )
    result = client.post(
        f"/api/internal/enrichment-jobs/{job['id']}/fail", headers=worker, json={"error": "extraction failed"}
    )
    assert result.json()["status"] == "failed"
    assert client.get(f"/api/admin/enrichment-jobs/{job['id']}").json()["error"] == "extraction failed"


def test_invalid_provider_output_keeps_usage_for_failure_review(client, db_engine, monkeypatch):
    item = program(client)
    monkeypatch.setenv("WINDMILL_URL", "http://windmill:8000")
    monkeypatch.setenv("WINDMILL_WORKSPACE", "bridge")
    monkeypatch.setenv("WINDMILL_FLOW_PATH", "f/bridge/enrich_funding_opportunity")
    monkeypatch.setenv("WINDMILL_API_TOKEN", "token")
    monkeypatch.setenv("BRIDGE_WORKER_API_KEY", "worker-secret")

    async def trigger(self, *_args):
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    monkeypatch.setattr(enrichment, "fetch_source", lambda _url: "Page content")
    monkeypatch.setattr(enrichment, "extract_fields", lambda _text, _url: (None, {"model": "test", "total_tokens": 11}))
    job = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    base = f"/api/internal/enrichment-jobs/{job['id']}"
    worker = {"X-Worker-Key": "worker-secret"}
    assert client.get(f"{base}/load?opportunity_id={item['id']}", headers=worker).status_code == 200
    assert client.post(f"{base}/fetch", headers=worker).status_code == 200
    assert client.post(f"{base}/extract", headers=worker).status_code == 422
    assert client.post(f"{base}/fail", headers=worker, json={"error": "invalid extraction"}).status_code == 200
    with Session(db_engine) as db:
        assert db.scalar(select(m.EnrichmentUsage)).total_tokens == 11


def test_versioned_flows_expose_separate_steps_and_failure_handler():
    root = Path(__file__).parents[1] / "bridge-windmill" / "flows"
    smoke = yaml.safe_load((root / "enrichment_smoke.flow" / "flow.yaml").read_text())
    full = yaml.safe_load((root / "enrich_funding_opportunity.flow" / "flow.yaml").read_text())
    assert [step["id"] for step in smoke["value"]["modules"]] == ["load", "smoke_complete"]
    assert [step["id"] for step in full["value"]["modules"]] == ["load", "fetch", "extract", "validate", "stage"]
    assert full["value"]["failure_module"]["id"] == "failure"
    assert full["schema"]["required"] == ["opportunity_id", "enrichment_job_id"]


def test_smoke_step_requires_development_flag(client, monkeypatch):
    item = program(client)
    monkeypatch.setenv("WINDMILL_URL", "http://windmill:8000")
    monkeypatch.setenv("WINDMILL_WORKSPACE", "bridge")
    monkeypatch.setenv("WINDMILL_FLOW_PATH", "f/bridge/enrichment_smoke")
    monkeypatch.setenv("WINDMILL_API_TOKEN", "token")
    monkeypatch.setenv("BRIDGE_WORKER_API_KEY", "worker-secret")

    async def trigger(self, *_args):
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    job = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    worker = {"X-Worker-Key": "worker-secret"}
    base = f"/api/internal/enrichment-jobs/{job['id']}"
    assert client.get(f"{base}/load?opportunity_id={item['id']}", headers=worker).status_code == 200
    assert client.post(f"{base}/smoke_complete", headers=worker).status_code == 404
    monkeypatch.setenv("BRIDGE_ENABLE_ENRICHMENT_SMOKE", "1")

    def variable(path):
        return {"f/bridge/api_url": "http://api:8000", "f/bridge/worker_api_key": "worker-secret"}[path]

    monkeypatch.setitem(sys.modules, "wmill", types.SimpleNamespace(get_variable=variable))

    def urlopen(request, timeout):
        assert timeout > 0
        result = client.request(
            request.get_method(),
            request.full_url.replace("http://api:8000", ""),
            headers=request.headers,
            content=request.data,
        )
        assert result.status_code == 200, result.text
        return io.BytesIO(result.content)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    flow = yaml.safe_load(
        (Path(__file__).parents[1] / "bridge-windmill/flows/enrichment_smoke.flow/flow.yaml").read_text()
    )
    for step in flow["value"]["modules"]:
        namespace = {}
        exec(step["value"]["content"], namespace)  # noqa: S102 - checked-in flow source
        namespace["main"](job["id"], step["id"], item["id"])
    assert client.get(f"/api/admin/enrichment-jobs/{job['id']}").json()["status"] == "succeeded"
    assert client.get(f"/opportunities/{item['id']}").json()["review_status"] == "pending"


def test_missing_and_contradictory_fields_are_flagged_and_rejection_preserves_record(client, monkeypatch):
    item = program(client)
    review = client.get("/review-queue").json()[0]
    client.post(f"/review-queue/{review['id']}/approve", json={})
    client.post(f"/opportunities/{item['id']}/publish")
    monkeypatch.setenv("WINDMILL_URL", "http://windmill:8000")
    monkeypatch.setenv("WINDMILL_WORKSPACE", "bridge")
    monkeypatch.setenv("WINDMILL_FLOW_PATH", "f/bridge/enrich_funding_opportunity")
    monkeypatch.setenv("WINDMILL_API_TOKEN", "token")
    monkeypatch.setenv("BRIDGE_WORKER_API_KEY", "worker-secret")

    async def trigger(self, *_args):
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    monkeypatch.setattr(enrichment, "fetch_source", lambda _url: "Grant amount from 100 to 200. Eligible in Canada.")
    monkeypatch.setattr(enrichment, "extract_fields", lambda _text, url: ({
        "amount_min": 200, "amount_max": 100, "geography": "Canada", "official_source_url": url,
        "evidence": [{"field": "geography", "source_url": url, "excerpt": "Eligible in Canada."}],
    }, {"model": "test", "total_tokens": 9}))
    job = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    base = f"/api/internal/enrichment-jobs/{job['id']}"
    worker = {"X-Worker-Key": "worker-secret"}
    assert client.get(f"{base}/load?opportunity_id={item['id']}", headers=worker).status_code == 200
    assert client.post(f"{base}/fetch", headers=worker).status_code == 200
    assert client.post(f"{base}/extract", headers=worker).status_code == 200
    proposal = client.post(f"{base}/validate", headers=worker).json()
    assert {"amount_min", "amount_max"} <= set(proposal["uncertain"])
    assert "organization_types" in proposal["missing"]
    assert "geography" not in proposal["uncertain"]
    assert client.post(f"{base}/stage", headers=worker).status_code == 200
    assert client.get(f"/api/admin/enrichment-jobs/{job['id']}/proposal").json() == proposal
    assert client.post(f"/api/admin/enrichment-jobs/{job['id']}/reject").json()["review_decision"] == "rejected"
    saved = client.get(f"/opportunities/{item['id']}").json()
    assert saved["summary"] == "Verified text"
    assert saved["publication_status"] == "published"


def test_directory_source_stops_before_fetch(client, monkeypatch):
    source = client.post("/sources", json={"name": "Directory", "base_url": "https://directory.example/",
                                           "kind": "directory", "resource_type": "funding_directory"}).json()
    item = client.post("/opportunities", json={"source_id": source["id"], "title": "Directory",
                                                 "funding_type": "grant", "url": source["base_url"]}).json()
    monkeypatch.setenv("WINDMILL_URL", "http://windmill:8000")
    monkeypatch.setenv("WINDMILL_WORKSPACE", "bridge")
    monkeypatch.setenv("WINDMILL_FLOW_PATH", "f/bridge/enrich_funding_opportunity")
    monkeypatch.setenv("WINDMILL_API_TOKEN", "token")
    monkeypatch.setenv("BRIDGE_WORKER_API_KEY", "worker-secret")

    async def trigger(self, *_args):
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    job = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    base = f"/api/internal/enrichment-jobs/{job['id']}"
    result = client.get(f"{base}/load?opportunity_id={item['id']}", headers={"X-Worker-Key": "worker-secret"})
    assert result.json()["classification"] == "directory"
    assert client.get(f"/api/admin/enrichment-jobs/{job['id']}").json()["stage"] == "discovery_required"
    assert client.post(f"{base}/fetch", headers={"X-Worker-Key": "worker-secret"}).status_code == 409


def test_openrouter_request_uses_schema_and_default_model(monkeypatch):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "response", "model": "google/gemini-2.5-flash-lite",
                                         "usage": {"total_tokens": 13},
                                         "choices": [{"message": {"content": '{"title":"Grant","summary":"Factual."}'}}]})

    real_client = httpx.Client

    def fake_client(*_args, **_kwargs):
        return real_client(transport=httpx.MockTransport(respond))

    monkeypatch.setattr(enrichment.httpx, "Client", fake_client)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    monkeypatch.delenv("BRIDGE_ENRICHMENT_MODEL", raising=False)
    fields, usages = enrichment.extract_fields("Source text", "https://fund.example/grant")
    usage = usages[0]
    assert len(usages) == 2
    request = seen[0]
    import json

    body = json.loads(request.content)
    assert request.headers["Authorization"] == "Bearer test-secret"
    assert body["model"] == "google/gemini-2.5-flash-lite"
    assert body["response_format"]["type"] == "json_schema"
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert body["max_completion_tokens"] == 2500
    assert fields["title"] == "Grant" and fields["geography"] is None
    assert usage["total_tokens"] == 13


def test_free_nemotron_preserves_output_budget_for_structured_json(monkeypatch):
    seen = []
    real_client = httpx.Client

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"model": "nvidia/nemotron-3.5-super-vl:free",
                                         "choices": [{"message": {"content": '{"title":"Grant"}'}}]})

    monkeypatch.setattr(enrichment.httpx, "Client", lambda *_args, **_kwargs: real_client(
        transport=httpx.MockTransport(respond)))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("BRIDGE_ENRICHMENT_MODEL", "nvidia/nemotron-3.5-super-vl:free")

    fields, _usages = enrichment.extract_fields("Source text", "https://fund.example/grant")

    import json

    assert fields["title"] == "Grant"
    assert json.loads(seen[0].content)["reasoning"] == {"enabled": False}


def test_openrouter_payment_failure_explains_billing_issue(monkeypatch):
    real_client = httpx.Client

    def fake_client(*_args, **_kwargs):
        return real_client(transport=httpx.MockTransport(lambda _request: httpx.Response(402)))

    monkeypatch.setattr(enrichment.httpx, "Client", fake_client)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")

    with pytest.raises(HTTPException) as error:
        enrichment.extract_fields("Source text", "https://fund.example/grant")

    assert error.value.status_code == 502
    assert "402" in error.value.detail
    assert "credit" in error.value.detail.lower()


def test_validation_maps_common_business_labels_to_review_category(client, monkeypatch):
    item = program(client)
    for key, value in {"WINDMILL_URL": "http://windmill:8000", "WINDMILL_WORKSPACE": "bridge",
                       "WINDMILL_FLOW_PATH": "f/bridge/enrich_funding_opportunity", "WINDMILL_API_TOKEN": "token",
                       "BRIDGE_WORKER_API_KEY": "worker-secret"}.items():
        monkeypatch.setenv(key, value)

    async def trigger(self, *_args):
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    monkeypatch.setattr(enrichment, "fetch_source", lambda _url: "Small businesses and startups may apply.")
    monkeypatch.setattr(enrichment, "extract_fields", lambda _text, _url: (
        {"title": "Grant", "organization_types": ["small business", "startup"]},
        {"model": "test", "total_tokens": 1},
    ))
    job = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    base = f"/api/internal/enrichment-jobs/{job['id']}"
    worker = {"X-Worker-Key": "worker-secret"}
    assert client.get(f"{base}/load?opportunity_id={item['id']}", headers=worker).status_code == 200
    assert client.post(f"{base}/fetch", headers=worker).status_code == 200
    assert client.post(f"{base}/extract", headers=worker).status_code == 200

    response = client.post(f"{base}/validate", headers=worker)

    assert response.status_code == 200
    assert response.json()["proposed"]["organization_types"] == ["business"]


def test_batch_dispatch_respects_concurrency_limit(client, monkeypatch):
    import asyncio

    source = client.post("/sources", json={"name": "Batch", "base_url": "https://batch.example", "kind": "website"}).json()
    items = [client.post("/opportunities", json={"source_id": source["id"], "title": f"Grant {i}",
                                                  "funding_type": "grant", "url": f"https://batch.example/{i}"}).json()
             for i in range(4)]
    for key, value in {"WINDMILL_URL": "http://windmill:8000", "WINDMILL_WORKSPACE": "bridge",
                       "WINDMILL_FLOW_PATH": "f/bridge/enrich_funding_opportunity", "WINDMILL_API_TOKEN": "token",
                       "BRIDGE_ENRICHMENT_CONCURRENCY": "2"}.items():
        monkeypatch.setenv(key, value)
    running = peak = 0
    received = []

    async def trigger(self, opportunity_id, job_id):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        received.append((opportunity_id, job_id))
        await asyncio.sleep(0.01)
        running -= 1
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    jobs = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"] for item in items]}).json()
    assert len(jobs) == 4 and peak == 2
    assert {(str(opportunity_id), str(job_id)) for opportunity_id, job_id in received} == {
        (job["opportunity_id"], job["id"]) for job in jobs}


def test_pdf_source_is_extracted_with_size_limit(monkeypatch):
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    output = io.BytesIO()
    writer.write(output)
    pdf = output.getvalue()

    def respond(_request):
        return httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})

    real_client = httpx.Client
    monkeypatch.setattr(enrichment.socket, "getaddrinfo", lambda *_args: [(None, None, None, None, ("8.8.8.8", 443))])
    monkeypatch.setattr(enrichment.httpx, "Client", lambda *_args, **_kwargs: real_client(transport=httpx.MockTransport(respond)))
    assert enrichment.fetch_source("https://fund.example/guidelines.pdf") == ""
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_full_flow_scripts_call_bridge_in_order(client, monkeypatch):
    item = program(client)
    monkeypatch.setenv("WINDMILL_URL", "http://windmill:8000")
    monkeypatch.setenv("WINDMILL_WORKSPACE", "bridge")
    monkeypatch.setenv("WINDMILL_FLOW_PATH", "f/bridge/enrich_funding_opportunity")
    monkeypatch.setenv("WINDMILL_API_TOKEN", "token")
    monkeypatch.setenv("BRIDGE_WORKER_API_KEY", "worker-secret")

    async def trigger(self, *_args):
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    monkeypatch.setattr(enrichment, "fetch_source", lambda _url: "Eligible in Canada. Grant amount 1000 CAD.")
    monkeypatch.setattr(enrichment, "extract_fields", lambda _text, url: ({
        "geography": "Canada", "amount_max": 1000, "currency": "cad", "summary": "A factual grant summary.",
        "funding_organization": "Grant Agency", "required_documents": ["Business plan"],
        "eligibility_rules": [{"criterion": "location", "requirement": "Canada", "source_url": url}],
        "evidence": [{"field": "amount_max", "source_url": url, "excerpt": "Grant amount 1000 CAD."},
                     {"field": "geography", "source_url": url, "excerpt": "Eligible in Canada."},
                     {"field": "eligibility_rules", "source_url": url, "excerpt": "Eligible in Canada."}],
    }, {"model": "test", "total_tokens": 12, "cost": 0.001}))
    job = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    monkeypatch.setitem(sys.modules, "wmill", types.SimpleNamespace(get_variable=lambda key: {
        "f/bridge/api_url": "http://api:8000", "f/bridge/worker_api_key": "worker-secret"}[key]))
    called = []

    def urlopen(request, timeout):
        called.append(request.full_url.rsplit("/", 1)[-1].split("?", 1)[0])
        result = client.request(request.get_method(), request.full_url.replace("http://api:8000", ""),
                                headers=request.headers, content=request.data)
        assert result.status_code == 200, result.text
        return io.BytesIO(result.content)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    flow = yaml.safe_load((Path(__file__).parents[1] /
                           "bridge-windmill/flows/enrich_funding_opportunity.flow/flow.yaml").read_text())
    for step in flow["value"]["modules"]:
        namespace = {}
        exec(step["value"]["content"], namespace)  # noqa: S102 - checked-in flow source
        namespace["main"](job["id"], step["id"], item["id"])
    assert called == ["load", "fetch", "extract", "validate", "stage"]
    saved_job = client.get(f"/api/admin/enrichment-jobs/{job['id']}").json()
    assert saved_job["display_status"] == "pending_review"
    assert saved_job["proposal"]["proposed"]["currency"] == "CAD"
    assert saved_job["proposal"]["extraction"]["cost_usd"] == 0.001
    assert client.get(f"/opportunities/{item['id']}").json()["amount_max"] is None
    accepted = client.post(f"/api/admin/enrichment-jobs/{job['id']}/approve", json={
        "accepted_fields": ["amount_max", "currency", "details", "eligibility_rules"]})
    assert accepted.status_code == 200, accepted.text
    saved = client.get(f"/opportunities/{item['id']}").json()
    assert saved["amount_max"] == 1000
    assert saved["details"]["funding_organization"] == "Grant Agency"
    assert saved["eligibility_rules"][0]["source_url"] == item["url"]
    versions = client.get(f"/opportunities/{item['id']}/versions").json()
    assert any(version["change_note"].startswith("Accepted enrichment proposal") for version in versions)


def test_short_summary_is_expanded_once(monkeypatch):
    calls = {"n": 0}
    real_client = httpx.Client
    long_summary = " ".join(["The fund supports women entrepreneurs across Canada with contribution funding."] * 6)

    def respond(request):
        calls["n"] += 1
        summary = "Too short." if calls["n"] == 1 else long_summary
        return httpx.Response(200, json={"id": f"response-{calls['n']}", "model": "google/gemini-2.5-flash-lite",
                                         "usage": {"total_tokens": calls["n"]},
                                         "choices": [{"message": {"content": f'{{"title":"Grant","summary":"{summary}"}}'}}]})

    monkeypatch.setattr(enrichment.httpx, "Client", lambda *_args, **_kwargs: real_client(transport=httpx.MockTransport(respond)))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    fields, usages = enrichment.extract_fields("Source text", "https://fund.example/grant")
    assert calls["n"] == 2
    assert len(fields["summary"].split()) >= 40
    assert [item["total_tokens"] for item in usages] == [1, 2]


def test_grounded_page_facts_replace_seed_notes(client, monkeypatch):
    source = client.post("/sources", json={"name": "ISED", "base_url": "https://www.ised-isde.canada.ca", "kind": "website"}).json()
    page = (
        "The call for proposals for the 2027 Women Entrepreneurship Strategy (WES) Ecosystem Fund is now open. "
        "Proposals may be submitted until November 9, 2026 (11:59 pm PST). "
        "Projects must be national or multi-regional; have a budget of between $250,000 and $6,000,000; "
        "and be led by a Canadian incorporated not-for-profit organization."
    )
    summary = " ".join(["This call funds ecosystem projects that support women entrepreneurs in Canada."] * 8)
    item = client.post("/opportunities", json={
        "source_id": source["id"], "title": "WES Ecosystem Fund", "funding_type": "grant",
        "url": "https://www.ised-isde.canada.ca/wes-ecosystem-fund",
        "summary": "Unverified seed lead. Reported audience: nonprofits. Seed notes: project budget $250k-$6m.",
        "geography": "Canada",
        "rounds": [{"name": "Seeded call; verify dates and cutoff time", "status": "unknown",
                    "application_url": "https://www.ised-isde.canada.ca/wes-ecosystem-fund"}],
    }).json()
    for key, value in {"WINDMILL_URL": "http://windmill:8000", "WINDMILL_WORKSPACE": "bridge",
                       "WINDMILL_FLOW_PATH": "f/bridge/enrich_funding_opportunity", "WINDMILL_API_TOKEN": "token",
                       "BRIDGE_WORKER_API_KEY": "worker-secret", "BRIDGE_AUTO_PUBLISH_ENRICHMENT": "1"}.items():
        monkeypatch.setenv(key, value)

    async def trigger(self, *_args):
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    monkeypatch.setattr(enrichment, "fetch_source", lambda _url: page)
    excerpt = "The call for proposals for the 2027 Women Entrepreneurship Strategy (WES) Ecosystem Fund is now open."
    monkeypatch.setattr(enrichment, "extract_fields", lambda _text, url: ({
        "title": "2027 WES Ecosystem Fund", "summary": summary, "currency": "cad",
        "amount_min": 250000, "amount_max": 6000000, "organization_types": ["not-for-profit organization"],
        "application_status": "open", "deadline": "2026-11-09T07:59:00-08:00",
        "eligible_applicants": "Canadian incorporated not-for-profit organizations.",
        "official_source_url": url,
        "evidence": [{"field": "title", "source_url": url, "excerpt": excerpt}],
    }, [{"model": "test", "total_tokens": 20}]))
    job = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    base = f"/api/internal/enrichment-jobs/{job['id']}"
    worker = {"X-Worker-Key": "worker-secret"}
    for step in ("load", "fetch", "extract", "validate", "stage"):
        response = client.get(f"{base}/load?opportunity_id={item['id']}", headers=worker) if step == "load" \
            else client.post(f"{base}/{step}", headers=worker)
        assert response.status_code == 200, response.text
    proposal = client.get(f"/api/admin/enrichment-jobs/{job['id']}/proposal").json()
    assert "summary" not in proposal["uncertain"]
    assert "amount_min" not in proposal["uncertain"] and "amount_max" not in proposal["uncertain"]
    assert "rounds" not in proposal["uncertain"]
    assert "organization_types" not in proposal["uncertain"]
    assert "summary" not in proposal["conflicts"]
    saved = client.get(f"/opportunities/{item['id']}").json()
    assert saved["summary"].startswith("This call funds")
    assert saved["amount_min"] == 250000 and saved["amount_max"] == 6000000 and saved["currency"] == "CAD"
    assert saved["organization_types"] == ["nonprofit"]
    assert saved["application_status"] == "open"
    assert saved["rounds"][0]["deadline"].startswith("2026-11-10T07:59:00")
    assert saved["publication_status"] == "published"
    assert "Unverified seed lead" not in saved["summary"]


def test_auto_publish_releases_supported_fields_and_unpublish_stays_off_explorer(client, monkeypatch):
    item = program(client)
    for key, value in {"WINDMILL_URL": "http://windmill:8000", "WINDMILL_WORKSPACE": "bridge",
                       "WINDMILL_FLOW_PATH": "f/bridge/enrich_funding_opportunity", "WINDMILL_API_TOKEN": "token",
                       "BRIDGE_WORKER_API_KEY": "worker-secret", "BRIDGE_AUTO_PUBLISH_ENRICHMENT": "1"}.items():
        monkeypatch.setenv(key, value)

    async def trigger(self, *_args):
        return uuid4()

    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    page = "Eligible in Canada. Grant amount from 100 to 200."
    monkeypatch.setattr(enrichment, "fetch_source", lambda _url: page)
    monkeypatch.setattr(enrichment, "extract_fields", lambda _text, url: ({
        "geography": "Canada", "currency": "cad", "amount_min": 200, "amount_max": 100,
        "official_source_url": url,
        "evidence": [{"field": "geography", "source_url": url, "excerpt": "Eligible in Canada."},
                     {"field": "currency", "source_url": url, "excerpt": "Eligible in Canada."}],
    }, {"model": "test", "total_tokens": 9}))
    job = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    base = f"/api/internal/enrichment-jobs/{job['id']}"
    worker = {"X-Worker-Key": "worker-secret"}
    for step in ("load", "fetch", "extract", "validate", "stage"):
        response = client.get(f"{base}/load?opportunity_id={item['id']}", headers=worker) if step == "load" \
            else client.post(f"{base}/{step}", headers=worker)
        assert response.status_code == 200, response.text

    saved = client.get(f"/opportunities/{item['id']}").json()
    assert saved["geography"] == "Canada"
    assert saved["currency"] == "CAD"
    assert saved["amount_min"] is None and saved["amount_max"] is None
    assert saved["verification_status"] == "approved"
    assert saved["publication_status"] == "published"
    assert client.get(f"/public/opportunities/{item['id']}").status_code == 200
    finished = client.get(f"/api/admin/enrichment-jobs/{job['id']}").json()
    assert finished["stage"] == "completed" and finished["review_decision"] == "approved"

    unpublished = client.post(f"/opportunities/{item['id']}/unpublish")
    assert unpublished.status_code == 200
    assert unpublished.json()["verification_status"] == "approved"
    assert unpublished.json()["publication_status"] == "unpublished"
    assert client.get(f"/public/opportunities/{item['id']}").status_code == 404

    monkeypatch.setattr(enrichment, "extract_fields", lambda _text, url: (
        {"currency": "usd", "official_source_url": url,
         "evidence": [{"field": "currency", "source_url": url, "excerpt": "Eligible in Canada."}]},
        {"model": "test", "total_tokens": 4},
    ))
    second = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    second_base = f"/api/internal/enrichment-jobs/{second['id']}"
    for step in ("load", "fetch", "extract", "validate", "stage"):
        response = client.get(f"{second_base}/load?opportunity_id={item['id']}", headers=worker) if step == "load" \
            else client.post(f"{second_base}/{step}", headers=worker)
        assert response.status_code == 200, response.text
    kept = client.get(f"/opportunities/{item['id']}").json()
    assert kept["currency"] == "USD"
    assert kept["verification_status"] == "approved"
    assert kept["publication_status"] == "unpublished"
    assert client.get(f"/public/opportunities/{item['id']}").status_code == 404


def test_page_eligibility_is_used_when_the_model_only_paraphrases():
    content = (
        "Admissibilité Pour être admissible, un organisme doit : "
        "Avoir son siège au Québec et réaliser majoritairement ses activités à Montréal; "
        "Offrir des activités à but non lucratif au bénéfice direct de la population montréalaise. "
        "Soumettre une demande Vous pouvez déposer une demande. "
        "Conditions d'admissibilité au programme Créavenir "
        "Avoir entre 18 et 39 ans Avoir une entreprise en démarrage (3 ans ou moins) "
        "Fonctionnement du programme"
    )
    rules = enrichment.eligibility_rules_from_extraction(
        {"eligible_applicants": "Non-profit organizations with headquarters in Quebec"},
        "https://montreal.ca/programmes/aide",
        content,
    )
    requirements = [rule["requirement"] for rule in rules]
    assert any("siège au Québec" in item for item in requirements)
    assert any("but non lucratif" in item for item in requirements)
    assert any(item == "Avoir entre 18 et 39 ans" for item in requirements)
    assert all("headquarters" not in item for item in requirements)
    assert all(rule["source_url"] == "https://montreal.ca/programmes/aide" for rule in rules)


def test_sourced_eligibility_and_past_and_future_rounds_are_published(client, monkeypatch):
    item = program(client)
    for key, value in {"WINDMILL_URL": "http://windmill:8000", "WINDMILL_WORKSPACE": "bridge",
                       "WINDMILL_FLOW_PATH": "f/bridge/enrich_funding_opportunity", "WINDMILL_API_TOKEN": "token",
                       "BRIDGE_WORKER_API_KEY": "worker-secret", "BRIDGE_AUTO_PUBLISH_ENRICHMENT": "1"}.items():
        monkeypatch.setenv(key, value)

    async def trigger(self, *_args):
        return uuid4()

    page = (
        "Applications for the 2024 call are now closed. The deadline was March 1, 2024. "
        "The 2027 call will open on January 15, 2027. "
        "Eligible organizations must be Canadian nonprofits with three years of operation."
    )
    monkeypatch.setattr(WindmillClient, "trigger", trigger)
    monkeypatch.setattr(enrichment, "fetch_source", lambda _url: page)
    monkeypatch.setattr(enrichment, "extract_fields", lambda _text, url: ({
        "eligible_applicants": "Canadian nonprofits with three years of operation",
        "funding_conditions": ["three years of operation"],
        "eligibility_rules": [
            {"criterion": "Organization", "requirement": "Canadian nonprofits", "source_url": url},
            {"criterion": "Location", "requirement": "Must operate on Mars", "source_url": "https://evil.example/rules"},
        ],
        "rounds": [
            {"name": "2024 call", "status": "closed", "deadline": "2024-03-01T00:00:00Z"},
            {"name": "2027 call", "status": "upcoming", "opens_at": "2027-01-15T00:00:00Z"},
        ],
    }, {"model": "test", "total_tokens": 11}))
    job = client.post("/api/admin/enrichment-jobs", json={"opportunity_ids": [item["id"]]}).json()[0]
    base = f"/api/internal/enrichment-jobs/{job['id']}"
    worker = {"X-Worker-Key": "worker-secret"}
    for step in ("load", "fetch", "extract", "validate", "stage"):
        response = client.get(f"{base}/load?opportunity_id={item['id']}", headers=worker) if step == "load" \
            else client.post(f"{base}/{step}", headers=worker)
        assert response.status_code == 200, response.text
    saved = client.get(f"/opportunities/{item['id']}").json()
    requirements = [rule["requirement"] for rule in saved["eligibility_rules"]]
    assert "Canadian nonprofits" in requirements
    assert "Canadian nonprofits with three years of operation" in requirements
    assert "three years of operation" not in requirements
    assert all("Mars" not in requirement for requirement in requirements)
    assert {(round_["name"], round_["status"]) for round_ in saved["rounds"]} == {
        ("2024 call", "closed"), ("2027 call", "upcoming"),
    }
    assert saved["application_status"] == "upcoming"
    assert saved["publication_status"] == "published"
