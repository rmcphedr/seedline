import asyncio
import os
from hmac import compare_digest
from typing import Literal
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.demo import router as demo_router
from backend import enrichment
from backend import models as m
from backend import schemas as s
from backend import services as service
from backend.db import get_db
from backend.discovery.cost import list_usage, usage_summary
from backend.discovery.runs import start_query_discovery
from backend.windmill import WindmillClient

app = FastAPI(title="Bridge API", version="0.1.0")
app.include_router(demo_router)


def admin_guard(x_admin_key: str | None = Header(default=None)):
    expected = os.getenv("ADMIN_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API key is not configured")
    if not x_admin_key or not compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Invalid admin key")


def worker_guard(x_worker_key: str | None = Header(default=None)):
    expected = os.getenv("BRIDGE_WORKER_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Worker API key is not configured")
    if not x_worker_key or not compare_digest(x_worker_key, expected):
        raise HTTPException(status_code=401, detail="Invalid worker key")


async def dispatch_enrichment(db: Session, jobs: list[m.EnrichmentJob]):
    limit = min(max(int(os.getenv("BRIDGE_ENRICHMENT_CONCURRENCY", "3")), 1), 10)
    semaphore = asyncio.Semaphore(limit)

    async def trigger(job: m.EnrichmentJob):
        async with semaphore:
            try:
                return await WindmillClient.from_env().trigger(job.opportunity_id, job.id)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                return exc

    results = await asyncio.gather(*(trigger(job) for job in jobs))
    for job, result in zip(jobs, results, strict=True):
        db.refresh(job)
        if isinstance(result, Exception):
            if job.status in {m.JobStatus.queued, m.JobStatus.running}:
                enrichment.fail(db, job.id, f"Windmill dispatch failed: {result}")
            continue
        try:
            job.windmill_job_id = result
            db.commit()
            db.refresh(job)
        except Exception:
            db.rollback()
            raise
    return jobs


@app.post(
    "/api/admin/enrichment-jobs",
    response_model=list[s.EnrichmentJobRead],
    status_code=201,
    dependencies=[Depends(admin_guard)],
)
async def create_enrichment_jobs(data: s.EnrichmentJobsCreate, db: Session = Depends(get_db)):
    jobs = enrichment.create_jobs(db, data.opportunity_ids)
    return await dispatch_enrichment(db, jobs)


@app.get("/api/admin/enrichment-jobs", response_model=list[s.EnrichmentJobRead], dependencies=[Depends(admin_guard)])
def list_enrichment_jobs(opportunity_id: UUID | None = None, db: Session = Depends(get_db)):
    return enrichment.list_jobs(db, opportunity_id)


@app.get("/api/admin/enrichment-jobs/{job_id}", response_model=s.EnrichmentJobRead, dependencies=[Depends(admin_guard)])
def get_enrichment_job(job_id: UUID, db: Session = Depends(get_db)):
    return service.require(db, m.EnrichmentJob, job_id)


@app.get("/api/admin/enrichment-jobs/{job_id}/proposal", dependencies=[Depends(admin_guard)])
def get_enrichment_proposal(job_id: UUID, db: Session = Depends(get_db)):
    job = service.require(db, m.EnrichmentJob, job_id)
    if not job.proposal:
        raise HTTPException(status_code=404, detail="Proposal is not available")
    return job.proposal


@app.post("/api/admin/enrichment-jobs/{job_id}/approve", response_model=s.EnrichmentJobRead,
          dependencies=[Depends(admin_guard)])
def approve_enrichment(job_id: UUID, data: s.EnrichmentReview, db: Session = Depends(get_db)):
    return enrichment.review(db, job_id, "approved", data)


@app.post("/api/admin/enrichment-jobs/{job_id}/reject", response_model=s.EnrichmentJobRead,
          dependencies=[Depends(admin_guard)])
def reject_enrichment(job_id: UUID, db: Session = Depends(get_db)):
    return enrichment.review(db, job_id, "rejected")


@app.post(
    "/api/admin/enrichment-jobs/{job_id}/retry",
    response_model=s.EnrichmentJobRead,
    status_code=201,
    dependencies=[Depends(admin_guard)],
)
async def retry_enrichment_job(job_id: UUID, db: Session = Depends(get_db)):
    old = service.require(db, m.EnrichmentJob, job_id)
    if old.status != m.JobStatus.failed:
        raise HTTPException(status_code=409, detail="Only failed jobs can be retried")
    jobs = enrichment.create_jobs(db, [old.opportunity_id], retry_of_id=old.id)
    return (await dispatch_enrichment(db, jobs))[0]


@app.get("/api/internal/enrichment-jobs/{job_id}/load", dependencies=[Depends(worker_guard)])
def worker_load(job_id: UUID, opportunity_id: UUID, db: Session = Depends(get_db)):
    return enrichment.load(db, job_id, opportunity_id)


@app.post("/api/internal/enrichment-jobs/{job_id}/fetch", dependencies=[Depends(worker_guard)])
def worker_fetch(job_id: UUID, db: Session = Depends(get_db)):
    return enrichment.fetch(db, job_id)


@app.post("/api/internal/enrichment-jobs/{job_id}/extract", dependencies=[Depends(worker_guard)])
def worker_extract(job_id: UUID, db: Session = Depends(get_db)):
    return enrichment.extract(db, job_id)


@app.post("/api/internal/enrichment-jobs/{job_id}/validate", dependencies=[Depends(worker_guard)])
def worker_validate(job_id: UUID, db: Session = Depends(get_db)):
    return enrichment.validate(db, job_id)


@app.post(
    "/api/internal/enrichment-jobs/{job_id}/stage",
    response_model=s.EnrichmentJobRead,
    dependencies=[Depends(worker_guard)],
)
def worker_stage(job_id: UUID, db: Session = Depends(get_db)):
    return enrichment.stage(db, job_id)


@app.post(
    "/api/internal/enrichment-jobs/{job_id}/fail",
    response_model=s.EnrichmentJobRead,
    dependencies=[Depends(worker_guard)],
)
def worker_fail(job_id: UUID, data: s.EnrichmentFailure, db: Session = Depends(get_db)):
    return enrichment.fail(db, job_id, data.error)


@app.post(
    "/api/internal/enrichment-jobs/{job_id}/smoke_complete",
    response_model=s.EnrichmentJobRead,
    dependencies=[Depends(worker_guard)],
)
def worker_smoke_complete(job_id: UUID, db: Session = Depends(get_db)):
    if os.getenv("BRIDGE_ENABLE_ENRICHMENT_SMOKE") != "1":
        raise HTTPException(status_code=404, detail="Smoke endpoint is disabled")
    return enrichment.complete_smoke(db, job_id)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/sources", response_model=s.SourceRead, status_code=201, dependencies=[Depends(admin_guard)])
def create_source(data: s.SourceCreate, db: Session = Depends(get_db)):
    return service.create_source(db, data)


@app.get("/sources", response_model=list[s.SourceRead], dependencies=[Depends(admin_guard)])
def list_sources(db: Session = Depends(get_db)):
    return service.list_sources(db)


@app.get("/sources/{item_id}", response_model=s.SourceRead, dependencies=[Depends(admin_guard)])
def get_source(item_id: UUID, db: Session = Depends(get_db)):
    return service.require(db, m.FundingSource, item_id)


@app.patch("/sources/{item_id}", response_model=s.SourceRead, dependencies=[Depends(admin_guard)])
def update_source(item_id: UUID, data: s.SourceUpdate, db: Session = Depends(get_db)):
    return service.update_source(db, item_id, data)


@app.delete("/sources/{item_id}", status_code=204, dependencies=[Depends(admin_guard)])
def delete_source(item_id: UUID, db: Session = Depends(get_db)):
    service.delete_source(db, item_id)
    return Response(status_code=204)


@app.post("/opportunities", response_model=s.OpportunityRead, status_code=201, dependencies=[Depends(admin_guard)])
def create_opportunity(data: s.OpportunityCreate, db: Session = Depends(get_db)):
    return service.create_opportunity(db, data)


@app.get("/opportunities", response_model=list[s.OpportunityRead], dependencies=[Depends(admin_guard)])
def list_opportunities(
    search: str | None = None,
    funding_type: m.FundingType | None = None,
    review_status: m.ReviewStatus | None = None,
    publication_status: Literal["published", "unpublished"] | None = None,
    geography: str | None = None,
    organization_type: Literal["business", "nonprofit", "individual", "cooperative"] | None = None,
    application_status: m.RoundStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_opportunities(
        db,
        search,
        funding_type,
        review_status,
        limit,
        offset,
        publication_status,
        geography,
        organization_type,
        application_status,
    )


@app.get("/opportunities/{item_id}", response_model=s.OpportunityRead, dependencies=[Depends(admin_guard)])
def get_opportunity(item_id: UUID, db: Session = Depends(get_db)):
    return service.require(db, m.FundingProgram, item_id)


@app.patch("/opportunities/{item_id}", response_model=s.OpportunityRead, dependencies=[Depends(admin_guard)])
def update_opportunity(item_id: UUID, data: s.OpportunityUpdate, db: Session = Depends(get_db)):
    return service.update_opportunity(db, item_id, data)


@app.get("/opportunities/{item_id}/versions", response_model=list[s.VersionRead], dependencies=[Depends(admin_guard)])
def list_opportunity_versions(item_id: UUID, db: Session = Depends(get_db)):
    return service.list_versions(db, item_id)


@app.post("/opportunities/{item_id}/publish", response_model=s.OpportunityRead, dependencies=[Depends(admin_guard)])
def publish_opportunity(item_id: UUID, db: Session = Depends(get_db)):
    return service.publish_opportunity(db, item_id)


@app.post("/opportunities/{item_id}/unpublish", response_model=s.OpportunityRead, dependencies=[Depends(admin_guard)])
def unpublish_opportunity(item_id: UUID, db: Session = Depends(get_db)):
    return service.unpublish_opportunity(db, item_id)


@app.get("/public/opportunities", response_model=list[s.OpportunityRead])
def list_public_opportunities(
    search: str | None = None,
    funding_type: m.FundingType | None = None,
    geography: str | None = None,
    organization_type: Literal["business", "nonprofit", "individual", "cooperative"] | None = None,
    application_status: m.RoundStatus | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_public_opportunities(
        db, search, funding_type, geography, organization_type, application_status, limit, offset
    )


@app.get("/public/opportunities/{item_id}", response_model=s.OpportunityRead)
def get_public_opportunity(item_id: UUID, db: Session = Depends(get_db)):
    return service.get_public_opportunity(db, item_id)


@app.post("/api/admin/discovery-runs", response_model=s.JobRead, status_code=201, dependencies=[Depends(admin_guard)])
def start_discovery_run(data: s.DiscoveryRunCreate, db: Session = Depends(get_db)):
    return start_query_discovery(db, data)


@app.post("/ingestion-jobs", response_model=s.JobRead, status_code=201, dependencies=[Depends(admin_guard)])
def create_job(data: s.JobCreate, db: Session = Depends(get_db)):
    return service.create_job(db, data)


@app.get("/ingestion-jobs", response_model=list[s.JobRead], dependencies=[Depends(admin_guard)])
def list_jobs(db: Session = Depends(get_db)):
    return service.list_jobs(db)


@app.get("/ingestion-jobs/{item_id}", response_model=s.JobRead, dependencies=[Depends(admin_guard)])
def get_job(item_id: UUID, db: Session = Depends(get_db)):
    return service.require(db, m.IngestionJob, item_id)


@app.get("/candidates", response_model=list[s.CandidateRead], dependencies=[Depends(admin_guard)])
def list_candidates(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_candidates(db, status, limit, offset)


@app.get("/candidates/{item_id}", response_model=s.CandidateRead, dependencies=[Depends(admin_guard)])
def get_candidate(item_id: UUID, db: Session = Depends(get_db)):
    return service.require(db, m.OpportunityCandidate, item_id)


@app.post("/candidates/{item_id}/dismiss", response_model=s.CandidateRead, dependencies=[Depends(admin_guard)])
def dismiss_candidate(item_id: UUID, db: Session = Depends(get_db)):
    return service.dismiss_candidate(db, item_id)


@app.post("/candidates/{item_id}/promote", response_model=s.CandidateRead, dependencies=[Depends(admin_guard)])
def promote_candidate(item_id: UUID, data: s.CandidatePromote, db: Session = Depends(get_db)):
    return service.promote_candidate(db, item_id, data)


@app.get("/discovery/usage-summary", response_model=s.UsageSummary, dependencies=[Depends(admin_guard)])
def get_discovery_usage(db: Session = Depends(get_db)):
    return usage_summary(db)


@app.get("/discovery/usage", response_model=list[s.UsageRead], dependencies=[Depends(admin_guard)])
def get_discovery_usage_events(
    job_id: UUID | None = None, limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db)
):
    return list_usage(db, job_id, limit)


@app.get("/review-queue", response_model=list[s.ReviewRead], dependencies=[Depends(admin_guard)])
def list_reviews(status: m.ReviewStatus = m.ReviewStatus.pending, db: Session = Depends(get_db)):
    return service.list_reviews(db, status)


@app.post("/review-queue/{item_id}/approve", response_model=s.ReviewRead, dependencies=[Depends(admin_guard)])
def approve(item_id: UUID, data: s.ReviewDecision, db: Session = Depends(get_db)):
    return service.decide_review(db, item_id, m.ReviewStatus.approved, data.note)


@app.post("/review-queue/{item_id}/reject", response_model=s.ReviewRead, dependencies=[Depends(admin_guard)])
def reject(item_id: UUID, data: s.ReviewDecision, db: Session = Depends(get_db)):
    return service.decide_review(db, item_id, m.ReviewStatus.rejected, data.note)


@app.post("/organizations", response_model=s.OrganizationRead, status_code=201, dependencies=[Depends(admin_guard)])
def create_organization(data: s.OrganizationCreate, db: Session = Depends(get_db)):
    return service.create_organization(db, data)


@app.get("/organizations", response_model=list[s.OrganizationRead], dependencies=[Depends(admin_guard)])
def list_organizations(db: Session = Depends(get_db)):
    return service.list_organizations(db)


@app.get("/organizations/{item_id}", response_model=s.OrganizationRead, dependencies=[Depends(admin_guard)])
def get_organization(item_id: UUID, db: Session = Depends(get_db)):
    return service.require(db, m.Organization, item_id)


@app.patch("/organizations/{item_id}", response_model=s.OrganizationRead, dependencies=[Depends(admin_guard)])
def update_organization(item_id: UUID, data: s.OrganizationUpdate, db: Session = Depends(get_db)):
    return service.update_organization(db, item_id, data)
