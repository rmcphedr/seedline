import csv
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.discovery.registry import load_registry, sync_registry
from backend.funding_seed import DEFAULT_SEED, import_funding_seed
from backend.models import (
    DiscoveryUsage,
    FundingProgram,
    FundingSource,
    IngestionJob,
    OpportunityCandidate,
    OpportunityVersion,
    ReviewQueue,
    ReviewStatus,
    RoundStatus,
)


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_full_seed_import_is_reviewable_and_audited(db_engine):
    with Session(db_engine) as db:
        registry = sync_registry(db, load_registry())
        result = import_funding_seed(db, DEFAULT_SEED)

        assert result.rows == 30
        assert result.programs_created == 12
        assert result.candidates_created == 4
        assert result.source_only_rows == 14
        assert count(db, FundingProgram) == 12
        assert count(db, ReviewQueue) == 12
        assert count(db, OpportunityCandidate) == 4
        assert count(db, DiscoveryUsage) == 0
        assert {p.review_status for p in db.scalars(select(FundingProgram))} == {ReviewStatus.pending}

        wes = db.scalar(select(FundingProgram).where(FundingProgram.title.like("2027 Women%")))
        assert wes.source_id == registry["wes_fund"].id
        assert wes.rounds[0].status == RoundStatus.unknown
        assert wes.rounds[0].deadline is None  # CSV has a date, but no cutoff time or time zone.
        assert wes.eligibility_rules == []
        snapshot = db.scalar(select(OpportunityVersion.snapshot).where(OpportunityVersion.program_id == wes.id))
        assert snapshot["seed_row"]["status_as_of_2026_10_26"] == "Open; deadline 2026-11-09"
        assert snapshot["seed_row"]["notes"].startswith("National or qualifying")

        candidate = db.scalar(select(OpportunityCandidate).where(OpportunityCandidate.title.like("National Research%")))
        assert candidate.status == "unverified"
        assert candidate.extracted_data["seed_row"]["funding_type"] == "Innovation project support"
        ced = db.scalar(select(OpportunityCandidate).where(OpportunityCandidate.title.like("CED – Regional Economic%")))
        assert ced.extracted_data["seed_row"]["funding_type"] == "Contributions"

        job = db.scalar(select(IngestionJob).where(IngestionJob.job_metadata["kind"].as_string() == "csv_seed_import"))
        assert len(job.job_metadata["rows"]) == 30
        assert job.job_metadata["model_calls"] == 0
        assert job.job_metadata["programs_created"] == 12
        assert job.job_metadata["candidates_created"] == 4
        assert db.get(FundingSource, wes.source_id).registry_key == "wes_fund"


def test_reimport_does_not_duplicate_or_overwrite_review(db_engine):
    with Session(db_engine) as db:
        first = import_funding_seed(db, DEFAULT_SEED)
        program = db.scalar(select(FundingProgram).where(FundingProgram.title.like("2027 Women%")))
        program.review_status = ReviewStatus.approved
        review = db.scalar(select(ReviewQueue).where(ReviewQueue.program_id == program.id))
        review.status = ReviewStatus.approved
        db.commit()

        second = import_funding_seed(db, DEFAULT_SEED)
        assert first.sources_created == 30
        assert second.sources_created == 0
        assert second.programs_created == 0
        assert second.candidates_created == 0
        assert count(db, IngestionJob) == 1
        assert count(db, FundingProgram) == 12
        assert count(db, FundingSource) == 30
        assert db.get(FundingProgram, program.id).review_status == ReviewStatus.approved


def test_invalid_csv_does_not_write_partial_import(db_engine, tmp_path):
    with DEFAULT_SEED.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    rows[1]["source_url"] = "javascript:alert(1)"
    path = Path(tmp_path) / "invalid.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with Session(db_engine) as db:
        with pytest.raises(ValueError, match="source_url"):
            import_funding_seed(db, path)
        assert count(db, FundingSource) == 0
        assert count(db, FundingProgram) == 0
        assert count(db, IngestionJob) == 0
