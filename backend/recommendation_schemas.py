"""Public contracts for local demo recommendations."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from backend.schemas import OpportunityRead


class CriterionAssessment(BaseModel):
    label: str
    requirement: str
    status: Literal["met", "not_met", "unknown"]
    explanation: str
    field: str | None = None
    unknown_reason: Literal["profile_missing", "opportunity_data_missing", "unsupported_rule"] | None = None
    source_rule_id: UUID | None = None
    source_url: str | None = None


class RecommendationRead(BaseModel):
    opportunity_id: UUID
    opportunity: OpportunityRead
    relevance_score: int | None
    score_breakdown: dict[str, int]
    eligibility_status: Literal["likely_eligible", "needs_information", "potentially_ineligible"]
    criteria: list[CriterionAssessment]
    matched_criteria: list[str]
    unmet_criteria: list[str]
    unknown_criteria: list[str]
    missing_profile_fields: list[str]
    industry_tags: list[str]
    deadline: str | None
    explanation: str


class RecommendationList(BaseModel):
    ready: bool
    missing_profile_fields: list[str]
    potentially_relevant_count: int
    items: list[RecommendationRead]
