from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import models as m
from backend import schemas as s


def require(db: Session, model: type, item_id: UUID):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return item


def save(db: Session, item):
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Record conflicts with existing data") from exc
    db.refresh(item)
    return item


def create_source(db: Session, data: s.SourceCreate):
    values = data.model_dump()
    values["base_url"] = str(data.base_url)
    return save(db, m.FundingSource(**values))


def list_sources(db: Session):
    return db.scalars(select(m.FundingSource).order_by(m.FundingSource.name)).all()


def update_source(db: Session, item_id: UUID, data: s.SourceUpdate):
    item = require(db, m.FundingSource, item_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, str(value) if key == "base_url" and value is not None else value)
    return save(db, item)


def delete_source(db: Session, item_id: UUID):
    item = require(db, m.FundingSource, item_id)
    db.delete(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Source has related records") from exc


def create_opportunity(db: Session, data: s.OpportunityCreate):
    if data.source_id:
        require(db, m.FundingSource, data.source_id)
    if data.amount_min is not None and data.amount_max is not None and data.amount_min > data.amount_max:
        raise HTTPException(status_code=422, detail="amount_min cannot exceed amount_max")
    for rule in data.eligibility_rules:
        if rule.document_id:
            require(db, m.SourceDocument, rule.document_id)
    values = data.model_dump(exclude={"rounds", "eligibility_rules"})
    if values.get("url"):
        values["url"] = str(values["url"])
    program = m.FundingProgram(**values)
    program.rounds = [m.FundingRound(**{**round_data.model_dump(), "application_url": str(round_data.application_url) if round_data.application_url else None}) for round_data in data.rounds]
    program.eligibility_rules = [m.EligibilityRule(**{**rule.model_dump(), "source_url": str(rule.source_url) if rule.source_url else None}) for rule in data.eligibility_rules]
    db.add(program)
    db.flush()
    db.add(m.ReviewQueue(program_id=program.id))
    db.add(m.OpportunityVersion(program_id=program.id, snapshot=data.model_dump(mode="json"), change_note="Created"))
    db.commit()
    db.refresh(program)
    return program


def list_opportunities(db: Session, search: str | None, funding_type: m.FundingType | None, review_status: m.ReviewStatus | None, limit: int, offset: int, publication_status: str | None = None, geography: str | None = None, organization_type: str | None = None, application_status: m.RoundStatus | None = None):
    query = select(m.FundingProgram)
    if search:
        query = query.where(m.FundingProgram.title.ilike(f"%{search}%"))
    if funding_type:
        query = query.where(m.FundingProgram.funding_type == funding_type)
    if review_status:
        query = query.where(m.FundingProgram.review_status == review_status)
    if publication_status == "published":
        query = query.where(m.FundingProgram.published_at.is_not(None))
    elif publication_status == "unpublished":
        query = query.where(m.FundingProgram.published_at.is_(None))
    if geography:
        query = query.where(m.FundingProgram.geography.ilike(f"%{geography}%"))
    programs = db.scalars(query.order_by(m.FundingProgram.created_at.desc())).all()
    if organization_type:
        programs = [program for program in programs if organization_type in program.organization_types]
    if application_status:
        programs = [program for program in programs if program.application_status == application_status]
    return programs[offset:offset + limit]


def update_opportunity(db: Session, item_id: UUID, data: s.OpportunityUpdate, *, commit: bool = True,
                       change_note: str = "Admin edited record; verification reset",
                       document_id: UUID | None = None):
    program = require(db, m.FundingProgram, item_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return program
    if data.source_id is not None:
        require(db, m.FundingSource, data.source_id)
    for rule in data.eligibility_rules or []:
        if rule.document_id:
            require(db, m.SourceDocument, rule.document_id)
    new_min = changes.get("amount_min", program.amount_min)
    new_max = changes.get("amount_max", program.amount_max)
    if new_min is not None and new_max is not None and new_min > new_max:
        raise HTTPException(status_code=422, detail="amount_min cannot exceed amount_max")
    for key, value in changes.items():
        if key == "rounds":
            program.rounds = [m.FundingRound(**{**round_data, "application_url": str(round_data["application_url"]) if round_data.get("application_url") else None}) for round_data in value]
        elif key == "eligibility_rules":
            program.eligibility_rules = [m.EligibilityRule(**{**rule_data, "source_url": str(rule_data["source_url"]) if rule_data.get("source_url") else None}) for rule_data in value]
        else:
            setattr(program, key, str(value) if key == "url" and value is not None else value)
    program.review_status = m.ReviewStatus.pending
    program.verified_at = None
    program.published_at = None
    review = db.scalar(select(m.ReviewQueue).where(m.ReviewQueue.program_id == program.id))
    if review is None:
        review = m.ReviewQueue(program_id=program.id)
        db.add(review)
    review.status = m.ReviewStatus.pending
    review.note = "Record changed; verification required"
    review.reviewed_at = None
    db.add(m.OpportunityVersion(program_id=program.id, document_id=document_id,
                                snapshot={"changes": data.model_dump(mode="json", exclude_unset=True)},
                                change_note=change_note))
    if commit:
        db.commit()
        db.refresh(program)
    else:
        db.flush()
    return program


def list_versions(db: Session, item_id: UUID):
    require(db, m.FundingProgram, item_id)
    return db.scalars(select(m.OpportunityVersion).where(m.OpportunityVersion.program_id == item_id).order_by(m.OpportunityVersion.created_at.desc())).all()


def publish_opportunity(db: Session, item_id: UUID):
    program = require(db, m.FundingProgram, item_id)
    if program.review_status != m.ReviewStatus.approved or program.verified_at is None:
        raise HTTPException(status_code=409, detail="Verify the opportunity before publication")
    if program.published_at is None:
        program.published_at = m.now()
        db.add(m.OpportunityVersion(program_id=program.id, snapshot={"publication_status": "published"}, change_note="Published"))
        db.commit()
        db.refresh(program)
    return program


def unpublish_opportunity(db: Session, item_id: UUID):
    program = require(db, m.FundingProgram, item_id)
    if program.published_at is not None:
        program.published_at = None
        db.add(m.OpportunityVersion(program_id=program.id, snapshot={"publication_status": "unpublished"}, change_note="Unpublished"))
        db.commit()
        db.refresh(program)
    return program


def list_public_opportunities(db: Session, search: str | None, funding_type: m.FundingType | None, geography: str | None, organization_type: str | None, application_status: m.RoundStatus | None, limit: int, offset: int):
    query = select(m.FundingProgram).where(
        m.FundingProgram.review_status == m.ReviewStatus.approved,
        m.FundingProgram.verified_at.is_not(None),
        m.FundingProgram.published_at.is_not(None),
    )
    if search:
        query = query.where(m.FundingProgram.title.ilike(f"%{search}%") | m.FundingProgram.summary.ilike(f"%{search}%"))
    if funding_type:
        query = query.where(m.FundingProgram.funding_type == funding_type)
    if geography:
        query = query.where(m.FundingProgram.geography.ilike(f"%{geography}%"))
    programs = db.scalars(query.order_by(m.FundingProgram.title)).all()
    if organization_type:
        programs = [program for program in programs if organization_type in program.organization_types]
    if application_status:
        programs = [program for program in programs if program.application_status == application_status]
    return programs[offset:offset + limit]


def get_public_opportunity(db: Session, item_id: UUID):
    program = require(db, m.FundingProgram, item_id)
    if program.review_status != m.ReviewStatus.approved or program.verified_at is None or program.published_at is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return program


def create_job(db: Session, data: s.JobCreate):
    if data.source_id:
        require(db, m.FundingSource, data.source_id)
    metadata = dict(data.metadata or {})
    if data.mode:
        metadata.update({"mode": data.mode, "query": data.query, "limit": data.limit})
    return save(db, m.IngestionJob(source_id=data.source_id, job_metadata=metadata))


def list_jobs(db: Session):
    return db.scalars(select(m.IngestionJob).order_by(m.IngestionJob.created_at.desc())).all()


def list_candidates(db: Session, status: str | None, limit: int, offset: int):
    query = select(m.OpportunityCandidate)
    if status:
        query = query.where(m.OpportunityCandidate.status == status)
    return db.scalars(query.order_by(m.OpportunityCandidate.updated_at.desc()).offset(offset).limit(limit)).all()


def dismiss_candidate(db: Session, candidate_id: UUID):
    candidate = require(db, m.OpportunityCandidate, candidate_id)
    if candidate.status != "unverified":
        raise HTTPException(status_code=409, detail="Candidate is already decided")
    candidate.status = "dismissed"
    return save(db, candidate)


def promote_candidate(db: Session, candidate_id: UUID, data: s.CandidatePromote):
    candidate = require(db, m.OpportunityCandidate, candidate_id)
    if candidate.status != "unverified":
        raise HTTPException(status_code=409, detail="Candidate is already decided")
    title = data.title or candidate.title
    if not title:
        raise HTTPException(status_code=422, detail="Candidate needs a title before promotion")
    extracted = candidate.extracted_data or {}
    summary = extracted.get("summary") if isinstance(extracted.get("summary"), str) else None
    geography = extracted.get("geography") if isinstance(extracted.get("geography"), str) else None
    program = m.FundingProgram(
        source_id=candidate.source_id, title=title, funding_type=data.funding_type,
        url=candidate.canonical_url or candidate.url, summary=summary, geography=geography,
        review_status=m.ReviewStatus.pending,
    )
    try:
        db.add(program)
        db.flush()
        db.add(m.ReviewQueue(program_id=program.id))
        db.add(m.OpportunityVersion(program_id=program.id, snapshot={
            "title": title, "funding_type": data.funding_type.value, "url": program.url,
            "summary": summary, "geography": geography,
            "candidate_id": str(candidate.id), "discovery_metadata": candidate.extracted_data,
        }, change_note="Promoted from discovery candidate for verification"))
        candidate.program_id = program.id
        candidate.status = "promoted"
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Candidate promotion conflicts with existing data") from exc
    db.refresh(candidate)
    return candidate


def list_reviews(db: Session, status: m.ReviewStatus):
    return db.scalars(select(m.ReviewQueue).where(m.ReviewQueue.status == status).order_by(m.ReviewQueue.created_at)).all()


def decide_review(db: Session, review_id: UUID, status: m.ReviewStatus, note: str | None):
    review = require(db, m.ReviewQueue, review_id)
    if review.status != m.ReviewStatus.pending:
        raise HTTPException(status_code=409, detail="Review already decided")
    review.status = status
    review.note = note
    review.reviewed_at = m.now()
    review.program.review_status = status
    review.program.verified_at = review.reviewed_at if status == m.ReviewStatus.approved else None
    if status != m.ReviewStatus.approved:
        review.program.published_at = None
    db.add(m.OpportunityVersion(program_id=review.program_id, snapshot={"review_status": status.value}, change_note=note or status.value))
    return save(db, review)


def create_organization(db: Session, data: s.OrganizationCreate):
    values = data.model_dump()
    if values.get("website"):
        values["website"] = str(values["website"])
    return save(db, m.Organization(**values))


def list_organizations(db: Session):
    return db.scalars(select(m.Organization).order_by(m.Organization.name)).all()


def update_organization(db: Session, item_id: UUID, data: s.OrganizationUpdate):
    item = require(db, m.Organization, item_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, str(value) if key == "website" and value is not None else value)
    return save(db, item)
