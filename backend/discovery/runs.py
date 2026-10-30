"""Start one admin discovery search. The route stays a thin wrapper around this module."""

import os
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import models as m
from backend import schemas as s
from backend.discovery.cost import CostRates
from backend.discovery.openrouter_provider import OpenRouterProvider, discovery_model
from backend.discovery.query import resolve_limit
from backend.models import now
from backend.services import create_job


def configuration_error() -> str | None:
    if not os.getenv("OPENROUTER_API_KEY"):
        return "OPENROUTER_API_KEY is not configured; no search was run"
    try:
        CostRates.from_env()
    except ValueError as exc:
        return f"{exc}; no search was run"
    return None


def provider_for_run():
    return OpenRouterProvider(), discovery_model(), CostRates.from_env()


def start_query_discovery(db: Session, data: s.DiscoveryRunCreate) -> m.IngestionJob:
    _expire_stuck_runs(db)
    active = db.scalars(select(m.IngestionJob).where(
        m.IngestionJob.status.in_([m.JobStatus.queued, m.JobStatus.running])
    )).all()
    if any((job.job_metadata or {}).get("kind") == "query_discovery" for job in active):
        raise HTTPException(status_code=409, detail="A discovery search is already running")
    source_id = data.source_id
    mode = "open"
    if source_id is not None:
        source = db.get(m.FundingSource, source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Funding source not found")
        if not source.active:
            raise HTTPException(status_code=422, detail="Choose an active source or search the open web")
        mode = "trusted"
    query = data.query.strip()
    job = create_job(db, s.JobCreate(
        source_id=source_id, mode=mode, query=query, limit=resolve_limit(query, data.limit),
        metadata={"kind": "query_discovery", "depth": "superficial"},
    ))
    error = configuration_error()
    if error:
        return _fail(db, job, error)
    from backend.discovery.runner import run_discovery_job

    try:
        provider, model, rates = provider_for_run()
        run_discovery_job(db, job.id, provider, model, rates)
    except Exception as exc:
        db.rollback()
        failed = db.get(m.IngestionJob, job.id)
        if failed is None:
            raise
        if failed.status == m.JobStatus.queued:
            return _fail(db, failed, str(exc)[:500] or "Discovery search failed")
        return failed
    return db.get(m.IngestionJob, job.id)


def _expire_stuck_runs(db: Session) -> None:
    cutoff = now() - timedelta(minutes=10)
    stuck = db.scalars(select(m.IngestionJob).where(
        m.IngestionJob.status.in_([m.JobStatus.queued, m.JobStatus.running])
    )).all()
    changed = False
    for job in stuck:
        if (job.job_metadata or {}).get("kind") != "query_discovery":
            continue
        started = _aware(job.started_at or job.created_at)
        if started >= cutoff:
            continue
        job.status = m.JobStatus.failed
        job.error = "Discovery search timed out before it finished"
        job.finished_at = now()
        changed = True
    if changed:
        db.commit()


def _fail(db: Session, job: m.IngestionJob, message: str) -> m.IngestionJob:
    job.status = m.JobStatus.failed
    job.error = message
    job.finished_at = now()
    db.commit()
    db.refresh(job)
    return job


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
