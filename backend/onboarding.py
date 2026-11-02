"""Persistence and session resolution for local-only founder onboarding."""

import hashlib
import secrets
from datetime import UTC, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend import models as m
from backend import onboarding_schemas as s
from backend.profile_completion import calculate

SESSION_LIFETIME = timedelta(days=7)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Profile data conflicts with an existing record") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Could not save profile right now") from exc


def create_demo(db: Session, display_name: str | None = None, *, example: bool = False) -> tuple[str, m.DemoSession]:
    founder = m.Founder(display_name=display_name.strip() or None if display_name else None,
                        demo_kind="example" if example else "fresh")
    organization = m.Organization(name="", kind="business", country="", industry=[])
    db.add_all([founder, organization])
    db.flush()
    membership = m.OrganizationMembership(founder_id=founder.id, organization_id=organization.id, role=None)
    intent = m.FundingIntent(organization_id=organization.id, is_primary=True)
    details = m.BusinessDetails(organization_id=organization.id)
    interests = m.FounderInterests(founder_id=founder.id)
    state = m.OnboardingState(organization_id=organization.id)
    if example:
        founder.display_name = "Alex Chen"
        founder.city, founder.province, founder.country = "Montreal", "QC", "CA"
        membership.role = "Co-founder"
        organization.name = "EcoPack Solutions"
        organization.description = "Reusable and compostable packaging for independent food businesses."
        organization.industry = ["sustainable_manufacturing"]
        organization.business_stage = "early_revenue"
        organization.country, organization.region, organization.city = "CA", "QC", "Montreal"
        organization.legal_structure = "corporation"
        organization.incorporation_status = "incorporated"
        intent.funding_purposes = ["equipment", "expansion"]
        intent.amount_min, intent.amount_max = 50000, 150000
        intent.preferred_funding_types = ["grant", "loan"]
        details.employee_count = 4
        details.annual_revenue_range = "100k_500k"
        state.current_step = "funding_goals"
        state.section_statuses = {"founder_basics": "completed", "business_overview": "completed"}
    token = secrets.token_urlsafe(32)
    session = m.DemoSession(
        token_hash=hashlib.sha256(token.encode()).hexdigest(), founder_id=founder.id,
        organization_id=organization.id, expires_at=m.now() + SESSION_LIFETIME,
    )
    db.add_all([membership, intent, details, interests, state, session])
    _commit(db)
    return token, session


def resolve_session(db: Session, token: str | None) -> m.DemoSession:
    if not token or len(token) > 200:
        raise HTTPException(status_code=401, detail="Start a local demo profile")
    digest = hashlib.sha256(token.encode()).hexdigest()
    session = db.scalar(select(m.DemoSession).where(m.DemoSession.token_hash == digest))
    if session is None:
        raise HTTPException(status_code=401, detail="Demo session was not found")
    expiry = session.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    if expiry <= m.now():
        raise HTTPException(status_code=401, detail="Demo session expired. Start a fresh demo")
    return session


def load(db: Session, session: m.DemoSession) -> tuple[m.Founder, m.OrganizationMembership, m.Organization, m.FundingIntent, m.BusinessDetails, m.FounderInterests, m.OnboardingState]:
    founder = db.get(m.Founder, session.founder_id)
    organization = db.get(m.Organization, session.organization_id)
    membership = db.scalar(select(m.OrganizationMembership).where(
        m.OrganizationMembership.founder_id == session.founder_id,
        m.OrganizationMembership.organization_id == session.organization_id,
    ))
    intent = db.scalar(select(m.FundingIntent).where(
        m.FundingIntent.organization_id == session.organization_id,
        m.FundingIntent.is_primary.is_(True),
    ))
    details = db.scalar(select(m.BusinessDetails).where(m.BusinessDetails.organization_id == session.organization_id))
    interests = db.scalar(select(m.FounderInterests).where(m.FounderInterests.founder_id == session.founder_id))
    state = db.scalar(select(m.OnboardingState).where(m.OnboardingState.organization_id == session.organization_id))
    if not all((founder, organization, membership, intent, details, interests, state)):
        raise HTTPException(status_code=401, detail="Demo profile is unavailable")
    return founder, membership, organization, intent, details, interests, state


def founder_read(founder: m.Founder, membership: m.OrganizationMembership) -> dict:
    return {
        "id": founder.id, "display_name": founder.display_name, "demo_kind": founder.demo_kind,
        "role": membership.role,
        "city": founder.city, "province": founder.province, "country": founder.country,
        "professional_background": founder.professional_background, "linkedin_url": founder.linkedin_url,
    }


def organization_read(organization: m.Organization) -> dict:
    return {
        "id": organization.id, "name": organization.name, "website": organization.website,
        "description": organization.description, "industry": organization.industry,
        "business_stage": organization.business_stage, "country": organization.country,
        "province": organization.region, "city": organization.city,
        "legal_structure": organization.legal_structure, "incorporation_status": organization.incorporation_status,
        "year_established": organization.year_established, "business_model": organization.business_model,
    }


def context(db: Session, session: m.DemoSession) -> dict:
    founder, membership, organization, intent, details, interests, state = load(db, session)
    return {
        "founder": founder_read(founder, membership), "organization": organization_read(organization),
        "funding_intent": intent, "details": details, "interests": interests,
        "onboarding": state,
        "completion": calculate(founder, membership, organization, intent, details, interests),
    }


def mark_provenance(db: Session, session: m.DemoSession, fields: list[str], source: str,
                    conversation_id: UUID | None = None) -> None:
    for field in fields:
        record = db.scalar(select(m.ProfileFieldProvenance).where(
            m.ProfileFieldProvenance.organization_id == session.organization_id,
            m.ProfileFieldProvenance.field == field,
        ))
        if record is None:
            record = m.ProfileFieldProvenance(organization_id=session.organization_id, field=field, source=source,
                                              conversation_id=conversation_id)
            db.add(record)
        else:
            record.source = source
            record.conversation_id = conversation_id


def patch_founder(db: Session, session: m.DemoSession, data: s.FounderPatch, *, commit: bool = True,
                  source: str = "manual", conversation_id: UUID | None = None) -> dict:
    founder, membership, *_ = load(db, session)
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "role":
            membership.role = value
        else:
            setattr(founder, key, str(value) if key == "linkedin_url" and value else value)
    mark_provenance(db, session, list(data.model_fields_set), source, conversation_id)
    if commit:
        _commit(db)
    return founder_read(founder, membership)


def patch_organization(db: Session, session: m.DemoSession, data: s.OrganizationPatch, *, commit: bool = True,
                       source: str = "manual", conversation_id: UUID | None = None) -> dict:
    _, _, organization, _, details, *_ = load(db, session)
    values = data.model_dump(exclude_unset=True)
    new_status = values.get("incorporation_status", organization.incorporation_status)
    new_year = values.get("year_established", organization.year_established)
    if new_status == "not_incorporated" and new_year is not None and "year_established" in values:
        raise HTTPException(status_code=422, detail="Year established is not applicable when not incorporated")
    if new_status == "not_incorporated":
        organization.year_established = None
    if new_status == "incorporated":
        details.years_in_operation = None
    for key, value in values.items():
        setattr(organization, "region" if key == "province" else key, str(value) if key == "website" and value else value)
    mark_provenance(db, session, list(values), source, conversation_id)
    if commit:
        _commit(db)
    return organization_read(organization)


def patch_funding_intent(db: Session, session: m.DemoSession, data: s.FundingIntentPatch, *, commit: bool = True,
                         source: str = "manual", conversation_id: UUID | None = None) -> m.FundingIntent:
    _, _, _, intent, *_ = load(db, session)
    values = data.model_dump(exclude_unset=True)
    amount_min = values.get("amount_min", intent.amount_min)
    amount_max = values.get("amount_max", intent.amount_max)
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        raise HTTPException(status_code=422, detail="Minimum amount cannot exceed maximum amount")
    if values.get("amount_unsure") is True:
        intent.amount_min = None
        intent.amount_max = None
    for key, value in values.items():
        setattr(intent, key, value)
    if "amount_min" in values or "amount_max" in values:
        intent.amount_unsure = False
    mark_provenance(db, session, list(values), source, conversation_id)
    if commit:
        _commit(db)
    return intent


def patch_details(db: Session, session: m.DemoSession, data: s.BusinessDetailsPatch, *, commit: bool = True,
                  source: str = "manual", conversation_id: UUID | None = None) -> m.BusinessDetails:
    _, _, organization, _, details, *_ = load(db, session)
    values = data.model_dump(exclude_unset=True)
    if organization.incorporation_status == "incorporated" and values.get("years_in_operation") is not None:
        raise HTTPException(status_code=422, detail="Years in operation is derived from year established")
    if values.get("previous_funding", details.previous_funding) in {"no", "unsure"}:
        if values.get("previous_funding_details"):
            raise HTTPException(status_code=422, detail="Funding history is not applicable")
        details.previous_funding_details = None
    for key, value in values.items():
        setattr(details, key, value)
    mark_provenance(db, session, list(values), source, conversation_id)
    if commit:
        _commit(db)
    return details


def patch_interests(db: Session, session: m.DemoSession, data: s.InterestsPatch, *, commit: bool = True,
                    source: str = "manual", conversation_id: UUID | None = None) -> m.FounderInterests:
    _, _, _, _, _, interests, _ = load(db, session)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(interests, key, value)
    mark_provenance(db, session, list(data.model_fields_set), source, conversation_id)
    if commit:
        _commit(db)
    return interests


def patch_onboarding(db: Session, session: m.DemoSession, data: s.OnboardingPatch) -> m.OnboardingState:
    *_, state = load(db, session)
    if data.current_step is not None:
        state.current_step = data.current_step
    if data.section_status is not None:
        state.section_statuses = {**state.section_statuses, data.current_step: data.section_status}
    if data.onboarding_status is not None:
        state.onboarding_status = data.onboarding_status
        state.completed_at = m.now() if data.onboarding_status == "finished" else None
    _commit(db)
    return state
