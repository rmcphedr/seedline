from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.discovery.catalog import comparable_url, guided_query, load_known_leads, title_key
from backend.discovery.cost import CostRates, record_usage
from backend.discovery.models import DiscoveredCandidate, ResearchResult, SelectionResult
from backend.discovery.normalize import canonicalize_url, known_source_ids
from backend.discovery.registry import load_registry
from backend.discovery.search import (
    candidates_from_citations,
    citation_titles,
    grounded_candidates,
    search_links_from_response,
)
from backend.models import FundingSource, IngestionJob, JobStatus, OpportunityCandidate, now


class DiscoveryProvider(Protocol):
    def research(
        self, query: str, model: str, allowed_domains: list[str] | None, limit: int, search_context_size: str = "medium"
    ) -> ResearchResult: ...

    def select(
        self, query: str, observed_urls: set[str], research_summary: str, model: str, limit: int
    ) -> SelectionResult: ...


def stage_candidate(
    db: Session, candidate: DiscoveredCandidate, source_id: UUID | None, job_id: UUID,
    source_keys: list[str], mode: str, query: str, response_id: str
) -> OpportunityCandidate:
    canonical = canonicalize_url(str(candidate.url))
    item = db.scalar(select(OpportunityCandidate).where(OpportunityCandidate.canonical_url == canonical))
    if item is None:
        item = OpportunityCandidate(url=canonical, canonical_url=canonical, status="unverified")
    if item.status == "unverified":
        item.title = candidate.title
    item.source_id = source_id or item.source_id
    item.job_id = job_id
    item.extracted_data = {
        "raw_url": str(candidate.url),
        "provider_hint": candidate.provider_hint,
        "type_hint": candidate.type_hint,
        "reason_to_investigate": candidate.reason_to_investigate,
        "summary": candidate.summary,
        "geography": candidate.geography,
        "audience": candidate.audience,
        "matched_source_keys": source_keys,
        "discovery_mode": mode,
        "search_query": query,
        "selection_response_id": response_id,
    }
    db.add(item)
    db.commit()
    return item


def run_discovery_job(
    db: Session, job_id: UUID, provider: DiscoveryProvider, model: str, rates: CostRates | None
) -> list[OpportunityCandidate]:
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise ValueError("Ingestion job not found")
    if job.status != JobStatus.queued:
        raise ValueError("Only queued jobs can run")
    metadata = job.job_metadata or {}
    mode = metadata.get("mode")
    query = metadata.get("query")
    limit = metadata.get("limit", 8)
    if mode not in ("open", "trusted") or not isinstance(query, str) or not query.strip() or not isinstance(limit, int) or not 1 <= limit <= 30:
        raise ValueError("Job needs a valid discovery mode, query, and limit")
    source = db.get(FundingSource, job.source_id) if job.source_id else None
    if mode == "trusted" and (source is None or not source.active):
        raise ValueError("Trusted discovery requires an active registered source")
    hostname = urlsplit(source.base_url).hostname if source else None
    allowed_domains = (source.allowed_domains or ([hostname] if hostname else [])) if mode == "trusted" else None
    if mode == "trusted" and not allowed_domains:
        raise ValueError("Trusted source needs allowed domains")
    superficial = metadata.get("depth") == "superficial"
    leads = load_known_leads(db)
    known_urls = {lead.url for lead in leads}
    known_titles = {lead.title_key for lead in leads if lead.title_key}
    base_query = f"{query}. Start with this trusted source: {source.name}: {source.base_url}" if source else query
    research_query = guided_query(base_query, leads, superficial=superficial)
    job.status = JobStatus.running
    job.started_at = now()
    db.commit()
    try:
        research = provider.research(
            research_query, model, allowed_domains, limit,
            search_context_size="low" if superficial else "medium",
        )
        record_usage(db, job.id, research.usage, rates)
        observed = search_links_from_response(research.payload)
        if not observed:
            raise RuntimeError("Research returned no cited or tool-sourced URLs")
        selection = provider.select(research_query, observed, research.summary, model, limit)
        record_usage(db, job.id, selection.usage, rates)
        if selection.error:
            raise RuntimeError(selection.error)
        accepted = grounded_candidates(selection.candidates, observed, allowed_domains, limit)
        accepted = candidates_from_citations(accepted, observed, research.payload, known_urls, allowed_domains, limit)
        registry = load_registry()
        staged = []
        skipped = []
        already_known = set(known_urls)
        titles = citation_titles(research.payload)
        for candidate in accepted:
            page = comparable_url(str(candidate.url))
            normalized_title = title_key(candidate.title)
            if page is None:
                continue
            if page in known_urls or (normalized_title and normalized_title in known_titles):
                skipped.append({
                    "title": candidate.title,
                    "url": page,
                    "match": "url" if page in known_urls else "title",
                })
                continue
            keys = known_source_ids(str(candidate.url), registry)
            assigned_source = source if source and mode == "trusted" else (
                db.scalar(select(FundingSource).where(FundingSource.registry_key == keys[0])) if keys else None
            )
            staged.append(stage_candidate(
                db, candidate, assigned_source.id if assigned_source else None, job.id,
                keys, mode, query, selection.response_id,
            ))
            known_urls.add(page)
            if normalized_title:
                known_titles.add(normalized_title)
            if len(staged) >= limit:
                break
        recorded = {item["url"] for item in skipped}
        for url in sorted(observed):
            page = comparable_url(url)
            if page and page in already_known and page not in recorded:
                skipped.append({"title": titles.get(url) or page, "url": page, "match": "url"})
                recorded.add(page)
        job = db.get(IngestionJob, job_id)
        metadata = dict(job.job_metadata or {})
        metadata["candidates_created"] = len(staged)
        metadata["duplicates_skipped"] = len(skipped)
        metadata["skipped"] = skipped[:20]
        job.job_metadata = metadata
        job.status = JobStatus.succeeded
        job.finished_at = now()
        db.commit()
        return staged
    except Exception as exc:
        db.rollback()
        job = db.get(IngestionJob, job_id)
        job.status = JobStatus.failed
        job.error = str(exc)[:2000]
        job.finished_at = now()
        db.commit()
        raise
