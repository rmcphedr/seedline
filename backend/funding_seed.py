"""Import a human-supplied CSV as reviewable leads and discovery sources.

CSV cells are data. They are never treated as instructions or verified source facts.
"""

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import SessionLocal
from backend.discovery.normalize import canonicalize_url
from backend.models import (
    FundingProgram,
    FundingRound,
    FundingSource,
    FundingType,
    IngestionJob,
    JobStatus,
    OpportunityCandidate,
    OpportunityVersion,
    ReviewQueue,
    ReviewStatus,
    RoundStatus,
    SourceKind,
    now,
)

DEFAULT_SEED = Path(__file__).resolve().parents[1] / "data" / "bridge_funding_seed_30.csv"
STATUS_COLUMN = "status_as_of_2026_10_26"
REQUIRED_COLUMNS = {
    "priority", "name", "provider", "resource_type", "funding_type", "geography",
    "target_audience", "source_url", STATUS_COLUMN, "notes",
}
PROGRAM_TYPES = {"specific_call", "financing_program"}
SOURCE_TYPES = {"funding_directory", "grantmaker_programs", "procurement_portal"}


@dataclass
class ImportResult:
    rows: int
    sources_created: int = 0
    programs_created: int = 0
    candidates_created: int = 0
    source_only_rows: int = 0
    already_imported: bool = False


def read_seed(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    seen_urls: set[str] = set()
    for number, row in enumerate(rows, start=2):
        if not row["name"] or not row["provider"]:
            raise ValueError(f"Row {number}: name and provider are required")
        if row["resource_type"] not in PROGRAM_TYPES | SOURCE_TYPES:
            raise ValueError(f"Row {number}: unknown resource_type: {row['resource_type']}")
        try:
            canonical = canonicalize_url(row["source_url"])
        except ValueError as exc:
            raise ValueError(f"Row {number}: invalid source_url") from exc
        if canonical in seen_urls:
            raise ValueError(f"Row {number}: duplicate source_url")
        seen_urls.add(canonical)
    return rows


def classify_funding_type(raw: str) -> FundingType | None:
    label = raw.casefold()
    if "loan" in label or "microloan" in label:
        return FundingType.loan
    if "grant" in label or "non-repayable contribution" in label:
        return FundingType.grant
    return None


def existing_by_url(items, url: str):
    return next((item for item in items if _canonical_or_none(item.url if hasattr(item, "url") else item.base_url) == url), None)


def _canonical_or_none(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return canonicalize_url(url)
    except ValueError:
        return None


def source_for_row(db: Session, row: dict[str, str], sources: list[FundingSource]) -> tuple[FundingSource, bool]:
    canonical = canonicalize_url(row["source_url"])
    existing = existing_by_url(sources, canonical)
    if existing is not None:
        existing.resource_type = row["resource_type"]
        return existing, False

    names = {source.name for source in sources}
    name = row["name"]
    if name in names:
        name = f"{name[:190]} (seed)"
    source = FundingSource(
        name=name,
        base_url=row["source_url"],
        kind=SourceKind.directory if row["resource_type"] in SOURCE_TYPES else SourceKind.website,
        resource_type=row["resource_type"],
        registry_key="csv_seed_" + hashlib.sha256(canonical.encode()).hexdigest()[:24],
        notes=f"Imported seed URL. Provider: {row['provider']}. Verify the official page before relying on it.",
    )
    db.add(source)
    db.flush()
    sources.append(source)
    return source, True


def import_funding_seed(db: Session, path: str | Path = DEFAULT_SEED) -> ImportResult:
    path = Path(path)
    rows = read_seed(path)  # Validate the whole file before writing anything.
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    result = ImportResult(rows=len(rows), source_only_rows=sum(row["resource_type"] in SOURCE_TYPES for row in rows))
    result.already_imported = any(
        (job.job_metadata or {}).get("kind") == "csv_seed_import"
        and (job.job_metadata or {}).get("sha256") == file_hash
        for job in db.scalars(select(IngestionJob))
    )
    sources = list(db.scalars(select(FundingSource)))
    programs = list(db.scalars(select(FundingProgram)))
    candidates = list(db.scalars(select(OpportunityCandidate)))

    try:
        for row in rows:
            source, created = source_for_row(db, row, sources)
            result.sources_created += int(created)
            if row["resource_type"] in SOURCE_TYPES:
                continue

            canonical = canonicalize_url(row["source_url"])
            if existing_by_url(programs, canonical) or existing_by_url(candidates, canonical):
                continue

            funding_type = classify_funding_type(row["funding_type"])
            if funding_type is None:
                candidate = OpportunityCandidate(
                    source_id=source.id,
                    url=row["source_url"],
                    canonical_url=canonical,
                    title=row["name"],
                    status="unverified",
                    extracted_data={"origin": "csv_seed", "seed_file": path.name, "seed_row": row},
                )
                db.add(candidate)
                candidates.append(candidate)
                result.candidates_created += 1
                continue

            program = FundingProgram(
                source_id=source.id,
                title=row["name"],
                funding_type=funding_type,
                summary=(
                    f"Unverified seed lead. Reported audience: {row['target_audience']}. "
                    f"Status reported as of 2026-10-26: {row[STATUS_COLUMN]}. "
                    f"Seed notes: {row['notes']}"
                ),
                url=row["source_url"],
                geography=row["geography"] or None,
                review_status=ReviewStatus.pending,
            )
            db.add(program)
            db.flush()
            if row["resource_type"] == "specific_call":
                db.add(FundingRound(
                    program_id=program.id,
                    name="Seeded call; verify dates and cutoff time",
                    status=RoundStatus.unknown,
                    application_url=row["source_url"],
                ))
            db.add(ReviewQueue(program_id=program.id, status=ReviewStatus.pending))
            db.add(OpportunityVersion(
                program_id=program.id,
                snapshot={"origin": "csv_seed", "seed_file": path.name, "seed_sha256": file_hash, "seed_row": row},
                change_note="Imported from CSV as an unverified lead",
            ))
            programs.append(program)
            result.programs_created += 1

        if not result.already_imported:
            timestamp = now()
            db.add(IngestionJob(
                status=JobStatus.succeeded,
                started_at=timestamp,
                finished_at=timestamp,
                job_metadata={
                    "kind": "csv_seed_import", "file": path.name, "sha256": file_hash,
                    "rows": rows, "model_calls": 0,
                    "programs_created": result.programs_created,
                    "candidates_created": result.candidates_created,
                    "source_only_rows": result.source_only_rows,
                },
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Import funding seed leads into DATABASE_URL without model calls")
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_SEED)
    args = parser.parse_args()
    with SessionLocal() as db:
        print(json.dumps(asdict(import_funding_seed(db, args.path)), indent=2))


if __name__ == "__main__":
    main()
