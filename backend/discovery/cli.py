"""Explicit discovery worker entry point; no scheduled or automatic model calls."""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    from backend.db import SessionLocal
    from backend.discovery.cost import CostRates, usage_summary
    from backend.discovery.registry import load_registry, sync_registry
    from backend.models import FundingSource, IngestionJob, OpportunityCandidate
    from backend.schemas import JobCreate
    from backend.services import create_job

    parser = argparse.ArgumentParser(prog="bridge-discovery")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("sources", help="List the curated source registry")
    actions.add_parser("sync-sources", help="Upsert the registry into funding_sources")
    actions.add_parser("candidates", help="List staged candidates")
    actions.add_parser("usage", help="Show this month's recorded API usage")
    queue = actions.add_parser("queue", help="Queue a discovery job without executing it")
    queue.add_argument("--mode", choices=["trusted", "open"], required=True)
    queue.add_argument("--source-key", help="Registry ID, required for trusted mode")
    queue.add_argument("--query", required=True)
    queue.add_argument("--limit", type=int, default=8)
    run = actions.add_parser("run-job", help="Preview or explicitly execute one queued job")
    run.add_argument("job_id")
    run.add_argument("--execute", action="store_true", help="Permit paid API calls")
    args = parser.parse_args(argv)

    if args.action == "sources":
        for source in load_registry().sources:
            print(f"{source.id:20} {source.kind:18} {source.name} | {source.url}")
        return 0

    with SessionLocal() as db:
        if args.action == "sync-sources":
            sources = sync_registry(db, load_registry())
            print(json.dumps({"synced_sources": len(sources)}))
        elif args.action == "candidates":
            rows = db.scalars(select(OpportunityCandidate).order_by(OpportunityCandidate.updated_at.desc()).limit(30)).all()
            print(json.dumps([{
                "id": str(row.id), "title": row.title, "url": row.canonical_url or row.url,
                "status": row.status, "source_id": str(row.source_id) if row.source_id else None,
            } for row in rows], indent=2))
        elif args.action == "usage":
            print(json.dumps(usage_summary(db), default=str, indent=2))
        elif args.action == "queue":
            if args.mode == "trusted" and not args.source_key:
                parser.error("--source-key is required for trusted mode")
            if not 1 <= args.limit <= 30:
                parser.error("--limit must be between 1 and 30")
            source = None
            if args.source_key:
                source = db.scalar(select(FundingSource).where(FundingSource.registry_key == args.source_key))
                if source is None:
                    parser.error("Source is not registered; run sync-sources first")
            job = create_job(db, JobCreate(source_id=source.id if source else None,
                                           mode=args.mode, query=args.query, limit=args.limit))
            print(json.dumps({"job_id": str(job.id), "status": job.status.value}))
        elif args.action == "run-job":
            from uuid import UUID

            try:
                job_id = UUID(args.job_id)
            except ValueError:
                parser.error("job_id must be a UUID")
            job = db.get(IngestionJob, job_id)
            if job is None:
                parser.error("Job not found")
            if not args.execute:
                print(json.dumps({"job_id": str(job.id), "status": job.status.value,
                                  "metadata": job.job_metadata, "will_call_api": False}, indent=2))
                return 0
            if not os.getenv("OPENAI_API_KEY"):
                parser.error("OPENAI_API_KEY is not configured; no API call was made")
            if not os.getenv("BRIDGE_DISCOVERY_MODEL"):
                parser.error("BRIDGE_DISCOVERY_MODEL is not configured; no API call was made")
            try:
                rates = CostRates.from_env()
            except ValueError as exc:
                parser.error(f"{exc}; no API call was made")
            if rates is None:
                parser.error("Configure all five rate variables before paid discovery; no API call was made")
            from backend.discovery.openai_provider import OpenAIProvider
            from backend.discovery.runner import run_discovery_job

            staged = run_discovery_job(db, job.id, OpenAIProvider(), os.environ["BRIDGE_DISCOVERY_MODEL"], rates)
            print(json.dumps({"job_id": str(job.id), "candidate_count": len(staged),
                              "monthly_usage": usage_summary(db)}, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
