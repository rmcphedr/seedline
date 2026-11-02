"""Demo assistant orchestration. Suggestions never become profile facts until confirmed."""

import os
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import assistant_provider, onboarding, onboarding_schemas, recommendations
from backend import assistant_questions as questions
from backend import assistant_schemas as s
from backend import models as m

FIELD_RESOURCE = {
    **dict.fromkeys(("name", "country", "province", "city", "description", "industry", "business_stage",
                     "legal_structure", "incorporation_status", "year_established"), "organization"),
    **dict.fromkeys(("funding_purposes", "preferred_funding_types", "amount_min", "amount_max",
                     "project_description"), "funding_intent"),
    **dict.fromkeys(("employee_count", "years_in_operation", "annual_revenue_range"), "details"),
}
PATCH_SCHEMA = {"organization": onboarding_schemas.OrganizationPatch,
                "funding_intent": onboarding_schemas.FundingIntentPatch,
                "details": onboarding_schemas.BusinessDetailsPatch}
PATCH_SERVICE = {"organization": onboarding.patch_organization,
                 "funding_intent": onboarding.patch_funding_intent,
                 "details": onboarding.patch_details}


def load_conversation(db: Session, session: m.DemoSession, conversation_id: UUID) -> m.AssistantConversation:
    conversation = db.scalar(select(m.AssistantConversation).where(
        m.AssistantConversation.id == conversation_id,
        m.AssistantConversation.founder_id == session.founder_id,
        m.AssistantConversation.organization_id == session.organization_id,
    ))
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _engine(db: Session, session: m.DemoSession, conversation_id: UUID, mode: str):
    if mode == "mock":
        return assistant_provider.MockProvider()

    def record(payload: dict, operation: str, model: str):
        usage = payload.get("usage") or {}
        with Session(db.get_bind()) as accounting:
            accounting.add(m.AssistantUsage(
                organization_id=session.organization_id, conversation_id=conversation_id,
                provider="openrouter", model=model, operation=operation,
                response_id=str(payload.get("id") or "")[:150] or None,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0), raw_usage=usage))
            accounting.commit()

    return assistant_provider.OpenRouterProvider(record)


def _question_engine(db: Session, session: m.DemoSession, conversation: m.AssistantConversation):
    try:
        return _engine(db, session, conversation.id, conversation.mode)
    except RuntimeError:
        return assistant_provider.MockProvider()


def state(db: Session, session: m.DemoSession, conversation: m.AssistantConversation) -> dict:
    messages = db.scalars(select(m.AssistantMessage).where(
        m.AssistantMessage.conversation_id == conversation.id).order_by(m.AssistantMessage.created_at, m.AssistantMessage.id)).all()
    suggestions = db.scalars(select(m.AssistantSuggestion).where(
        m.AssistantSuggestion.conversation_id == conversation.id).order_by(m.AssistantSuggestion.created_at, m.AssistantSuggestion.id)).all()
    provenance = db.scalars(select(m.ProfileFieldProvenance).where(
        m.ProfileFieldProvenance.organization_id == session.organization_id)).all()
    program = db.get(m.FundingProgram, conversation.opportunity_id) if conversation.opportunity_id else None
    return {"id": conversation.id, "mode": conversation.mode, "opportunity_id": conversation.opportunity_id,
            "opportunity_title": program.title if program else None, "messages": messages,
            "suggestions": suggestions, "provenance": {item.field: item.source for item in provenance},
            "completion_percent": onboarding.context(db, session)["completion"]["overall_completion"]}


def _compact_context(db: Session, session: m.DemoSession, conversation: m.AssistantConversation) -> dict:
    profile = questions.profile_values(db, session)
    recent = db.scalars(select(m.AssistantMessage).where(m.AssistantMessage.conversation_id == conversation.id)
                        .order_by(m.AssistantMessage.created_at.desc(), m.AssistantMessage.id.desc()).limit(4)).all()
    # Only business fields useful for this turn, and at most four short recent messages.
    useful = {"name", "country", "province", "city", "industry", "business_stage", "legal_structure",
              "incorporation_status", "funding_purposes"}
    return {"profile": {key: value for key, value in profile.items() if key in useful and value not in (None, "", [])},
            "recent": [{"role": item.role, "content": item.content[:350]} for item in reversed(recent)]}


def _next_question(db: Session, session: m.DemoSession, conversation: m.AssistantConversation,
                   engine: assistant_provider.ExtractionProvider) -> m.AssistantMessage:
    asked = set(db.scalars(select(m.AssistantMessage.target_field).where(
        m.AssistantMessage.conversation_id == conversation.id,
        m.AssistantMessage.role == "assistant",
        m.AssistantMessage.target_field.is_not(None))).all())
    field, title, requirement = questions.select_field(db, session, conversation.opportunity_id, asked)
    if field is None:
        content = "Your profile covers the main questions I can check. You can describe another detail or review your funding matches."
    else:
        template = questions.question(field, title, requirement)
        context = _compact_context(db, session, conversation)
        if requirement:
            context["selected_requirement"] = requirement[:300]
        content = engine.word_question(field, template, context)
    message = m.AssistantMessage(conversation_id=conversation.id, role="assistant", content=content,
                                 target_field=field)
    db.add(message)
    return message


def start(db: Session, session: m.DemoSession, request: s.StartConversation) -> dict:
    mode = os.getenv("SEEDLINE_ASSISTANT_MODE", "mock").lower()
    if mode not in {"mock", "live"}:
        raise HTTPException(status_code=503, detail="SEEDLINE_ASSISTANT_MODE must be mock or live")
    if request.opportunity_id:
        recommendations.get_for_session(db, session, request.opportunity_id)
    if not request.restart:
        existing = db.scalar(select(m.AssistantConversation).where(
            m.AssistantConversation.founder_id == session.founder_id,
            m.AssistantConversation.organization_id == session.organization_id,
            m.AssistantConversation.opportunity_id == request.opportunity_id,
        ).order_by(m.AssistantConversation.created_at.desc()).limit(1))
        if existing:
            return state(db, session, existing)
    conversation = m.AssistantConversation(founder_id=session.founder_id, organization_id=session.organization_id,
                                           opportunity_id=request.opportunity_id, mode=mode)
    db.add(conversation)
    db.flush()
    try:
        engine = _engine(db, session, conversation.id, mode)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    profile = questions.profile_values(db, session)
    if not request.opportunity_id and not any(profile[key] for key in ("description", "industry", "funding_purposes")):
        db.add(m.AssistantMessage(conversation_id=conversation.id, role="assistant", target_field="description",
                                  content="Tell me a little about your business. What are you building, and who is it for?"))
    else:
        _next_question(db, session, conversation, engine)
    db.commit()
    return state(db, session, conversation)


def _validated_fields(message: str, extracted: list[dict], profile: dict) -> list[dict]:
    candidates: dict[str, list[dict]] = {}
    for item in extracted[:30]:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        resource = FIELD_RESOURCE.get(field)
        source = item.get("source_text")
        confidence = item.get("confidence")
        if not resource or not isinstance(source, str) or not source.strip() or source.casefold() not in message.casefold() or \
                confidence not in {"high", "medium", "low"}:
            continue
        value = item.get("value")
        if value is None or field == "description" and (not isinstance(value, str) or value.strip() not in message):
            continue
        try:
            validated = PATCH_SCHEMA[resource].model_validate({field: value}).model_dump(exclude_unset=True)[field]
        except (ValidationError, KeyError, TypeError):
            continue
        if validated == profile.get(field):
            continue
        candidates.setdefault(field, []).append({"field": field, "resource": resource, "value": validated,
            "confidence": confidence, "source_text": source.strip()[:500], "base_value": profile.get(field)})
    # Two conflicting readings of the same field need another founder answer.
    validated = [items[0] for items in candidates.values() if all(item["value"] == items[0]["value"] for item in items)]
    # A confirmed Quebec or Ontario location has an unambiguous country, even if the model omits it.
    province = next((item for item in validated if item["field"] == "province" and item["value"] in {"QC", "ON"}), None)
    if province and not candidates.get("country") and not profile.get("country"):
        validated.append({"field": "country", "resource": "organization", "value": "CA",
                          "confidence": "medium", "source_text": province["source_text"],
                          "base_value": profile.get("country")})
    return validated


def send(db: Session, session: m.DemoSession, conversation_id: UUID, request: s.SendMessage) -> dict:
    conversation = load_conversation(db, session, conversation_id)
    duplicate = db.scalar(select(m.AssistantMessage).where(
        m.AssistantMessage.conversation_id == conversation.id,
        m.AssistantMessage.request_id == request.request_id))
    if duplicate:
        return state(db, session, conversation)
    if db.scalar(select(m.AssistantSuggestion.id).where(
        m.AssistantSuggestion.conversation_id == conversation.id, m.AssistantSuggestion.status == "pending").limit(1)):
        raise HTTPException(status_code=409, detail="Review pending suggestions before sending another message")
    last = db.scalar(select(m.AssistantMessage).where(m.AssistantMessage.conversation_id == conversation.id,
        m.AssistantMessage.role == "assistant").order_by(m.AssistantMessage.created_at.desc(), m.AssistantMessage.id.desc()).limit(1))
    try:
        engine = _engine(db, session, conversation.id, conversation.mode)
        extracted = engine.extract(request.content.strip(), last.target_field if last else None,
                                   _compact_context(db, session, conversation))
    except (httpx.HTTPError, RuntimeError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=503, detail="Assistant extraction is unavailable. Retry or use manual onboarding.") from exc
    validated = _validated_fields(request.content.strip(), extracted, questions.profile_values(db, session))
    try:
        user = m.AssistantMessage(conversation_id=conversation.id, role="user", content=request.content.strip(),
                                  request_id=request.request_id)
        db.add(user)
        db.flush()
        for item in validated:
            db.add(m.AssistantSuggestion(conversation_id=conversation.id, message_id=user.id, **item))
        reply = f"I found {len(validated)} profile detail{'s' if len(validated) != 1 else ''} for you to review below. Nothing changes until you confirm." if validated else \
                "I couldn't identify a profile detail from that answer. Could you clarify or skip this question?"
        db.add(m.AssistantMessage(conversation_id=conversation.id, role="assistant", content=reply,
                                  target_field=last.target_field if not validated and last else None))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        duplicate = db.scalar(select(m.AssistantMessage).where(
            m.AssistantMessage.conversation_id == conversation_id,
            m.AssistantMessage.request_id == request.request_id))
        if duplicate:
            return state(db, session, load_conversation(db, session, conversation_id))
        raise HTTPException(status_code=409, detail="Could not save this message") from exc
    return state(db, session, conversation)


def confirm(db: Session, session: m.DemoSession, conversation_id: UUID, request: s.ConfirmSuggestions) -> dict:
    conversation = load_conversation(db, session, conversation_id)
    ids = [item.id for item in request.decisions]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Each suggestion may be decided once")
    suggestions = db.scalars(select(m.AssistantSuggestion).where(
        m.AssistantSuggestion.conversation_id == conversation.id,
        m.AssistantSuggestion.id.in_(ids)).with_for_update()).all()
    by_id = {item.id: item for item in suggestions}
    if len(by_id) != len(ids):
        raise HTTPException(status_code=404, detail="Suggestion not found")
    profile = questions.profile_values(db, session)
    patches: dict[str, dict] = {}
    newly_decided = []
    for decision in request.decisions:
        item = by_id[decision.id]
        target_status = "accepted" if decision.action == "accept" else "rejected"
        if item.status != "pending":
            if item.status != target_status or decision.value is not None and decision.value != item.value:
                raise HTTPException(status_code=409, detail="Suggestion was already decided differently")
            continue
        if decision.action == "accept":
            if profile.get(item.field) != item.base_value:
                raise HTTPException(status_code=409, detail="Profile changed since this suggestion. Send a new answer.")
            value = item.value if decision.value is None else decision.value
            try:
                value = PATCH_SCHEMA[item.resource].model_validate({item.field: value}).model_dump(exclude_unset=True)[item.field]
            except (ValidationError, KeyError, TypeError) as exc:
                raise HTTPException(status_code=422, detail=f"Invalid value for {item.field}") from exc
            patches.setdefault(item.resource, {})[item.field] = value
            item.value = value
        newly_decided.append((item, target_status))
    try:
        for resource, values in patches.items():
            PATCH_SERVICE[resource](db, session, PATCH_SCHEMA[resource].model_validate(values), commit=False,
                                    source="ai_confirmed", conversation_id=conversation.id)
        for item, target_status in newly_decided:
            item.status = target_status
        db.flush()
        pending = db.scalar(select(m.AssistantSuggestion.id).where(
            m.AssistantSuggestion.conversation_id == conversation.id, m.AssistantSuggestion.status == "pending").limit(1))
        if newly_decided and not pending:
            engine = _question_engine(db, session, conversation)
            _next_question(db, session, conversation, engine)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return state(db, session, conversation)


def skip(db: Session, session: m.DemoSession, conversation_id: UUID) -> dict:
    conversation = load_conversation(db, session, conversation_id)
    if db.scalar(select(m.AssistantSuggestion.id).where(
        m.AssistantSuggestion.conversation_id == conversation.id, m.AssistantSuggestion.status == "pending").limit(1)):
        raise HTTPException(status_code=409, detail="Review pending suggestions first")
    engine = _question_engine(db, session, conversation)
    _next_question(db, session, conversation, engine)
    db.commit()
    return state(db, session, conversation)
