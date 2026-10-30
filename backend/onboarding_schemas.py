from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Industry = Literal[
    "technology", "manufacturing", "sustainable_manufacturing", "health", "food_agriculture",
    "retail", "professional_services", "creative", "education", "clean_energy", "social_impact", "other",
]
Stage = Literal["idea", "pre_launch", "prototype", "early_revenue", "growth", "established"]
Step = Literal["founder_basics", "business_overview", "funding_goals", "business_details", "founder_interests"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DemoCreate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)


class FounderPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    province: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    professional_background: str | None = Field(default=None, max_length=5000)
    linkedin_url: HttpUrl | None = None


class FounderRead(ORMModel):
    id: UUID
    display_name: str | None
    demo_kind: str | None
    role: str | None = None
    city: str | None
    province: str | None
    country: str | None
    professional_background: str | None
    linkedin_url: str | None


class OrganizationPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    website: HttpUrl | None = None
    description: str | None = Field(default=None, max_length=10000)
    industry: list[Industry] | None = Field(default=None, max_length=6)
    business_stage: Stage | None = None
    country: str | None = Field(default=None, max_length=2)
    province: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=120)
    legal_structure: Literal["sole_proprietorship", "corporation", "partnership", "cooperative", "nonprofit", "other"] | None = None
    incorporation_status: Literal["incorporated", "not_incorporated", "in_progress", "unsure"] | None = None
    year_established: int | None = Field(default=None, ge=1800, le=2100)
    business_model: Literal["b2b", "b2c", "b2g", "mixed"] | None = None

    @model_validator(mode="after")
    def conditional_year(self):
        for key in ("name", "country", "industry"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        if self.country and len(self.country) != 2:
            raise ValueError("country must be a two-letter code")
        if self.incorporation_status == "not_incorporated" and self.year_established is not None:
            raise ValueError("year_established is not applicable when not incorporated")
        if self.year_established is not None and self.year_established > datetime.now().year:
            raise ValueError("year_established cannot be in the future")
        return self


class OrganizationRead(ORMModel):
    id: UUID
    name: str
    website: str | None
    description: str | None
    industry: list[str]
    business_stage: str | None
    country: str
    province: str | None = None
    city: str | None
    legal_structure: str | None
    incorporation_status: str | None
    year_established: int | None
    business_model: str | None


class FundingIntentPatch(BaseModel):
    project_description: str | None = Field(default=None, max_length=10000)
    funding_purposes: list[Literal["research", "product", "equipment", "hiring", "marketing", "expansion", "training", "launch", "other"]] | None = Field(default=None, max_length=9)
    amount_min: int | None = Field(default=None, ge=0)
    amount_max: int | None = Field(default=None, ge=0)
    amount_unsure: bool | None = None
    funding_timeline: Literal["immediately", "within_6_months", "within_12_months", "flexible", "unsure"] | None = None
    preferred_funding_types: list[Literal["grant", "loan", "equity", "accelerator", "competition", "other"]] | None = Field(default=None, max_length=6)

    @model_validator(mode="after")
    def validate_range(self):
        for key in ("funding_purposes", "preferred_funding_types"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        if self.amount_unsure is True and (self.amount_min is not None or self.amount_max is not None):
            raise ValueError("amounts must be empty when amount_unsure is true")
        if self.amount_min is not None and self.amount_max is not None and self.amount_min > self.amount_max:
            raise ValueError("amount_min cannot exceed amount_max")
        return self


class FundingIntentRead(ORMModel):
    id: UUID
    project_description: str | None
    funding_purposes: list[str]
    amount_min: int | None
    amount_max: int | None
    amount_unsure: bool | None
    funding_timeline: str | None
    preferred_funding_types: list[str]


class BusinessDetailsPatch(BaseModel):
    employee_count: int | None = Field(default=None, ge=0, le=1000000)
    years_in_operation: int | None = Field(default=None, ge=0, le=200)
    annual_revenue_range: Literal["pre_revenue", "under_100k", "100k_500k", "500k_1m", "1m_5m", "over_5m", "unsure"] | None = None
    previous_funding: Literal["yes", "no", "unsure"] | None = None
    previous_funding_details: str | None = Field(default=None, max_length=5000)
    current_funding_status: Literal["not_seeking", "exploring", "applying", "funded", "unsure"] | None = None
    ownership_eligibility: list[Literal["woman_owned", "indigenous_owned", "black_owned", "other_underrepresented", "none", "prefer_not_to_say"]] | None = Field(default=None, max_length=6)

    @model_validator(mode="after")
    def conditional_history(self):
        if self.previous_funding in {"no", "unsure"} and self.previous_funding_details:
            raise ValueError("previous_funding_details is not applicable without previous funding")
        return self


class BusinessDetailsRead(ORMModel):
    employee_count: int | None
    years_in_operation: int | None
    annual_revenue_range: str | None
    previous_funding: str | None
    previous_funding_details: str | None
    current_funding_status: str | None
    ownership_eligibility: list[str] | None


class InterestsPatch(BaseModel):
    expertise: list[str] | None = Field(default=None, max_length=12)
    challenges: list[str] | None = Field(default=None, max_length=12)
    support_areas: list[str] | None = Field(default=None, max_length=12)
    mentorship_interest: bool | None = None
    collaboration_interest: bool | None = None
    connections_opt_in: bool | None = None

    @model_validator(mode="after")
    def validate_lists(self):
        for key in ("expertise", "challenges", "support_areas"):
            value = getattr(self, key)
            if key in self.model_fields_set and value is None:
                raise ValueError(f"{key} cannot be null")
            if value is not None and any(len(item) > 120 for item in value):
                raise ValueError(f"{key} entries must be at most 120 characters")
        return self


class InterestsRead(ORMModel):
    expertise: list[str]
    challenges: list[str]
    support_areas: list[str]
    mentorship_interest: bool | None
    collaboration_interest: bool | None
    connections_opt_in: bool | None


class OnboardingPatch(BaseModel):
    current_step: Step | None = None
    section_status: Literal["not_started", "in_progress", "completed", "skipped"] | None = None
    onboarding_status: Literal["in_progress", "finished"] | None = None

    @model_validator(mode="after")
    def status_needs_step(self):
        if self.section_status is not None and self.current_step is None:
            raise ValueError("section_status requires current_step")
        return self


class OnboardingRead(ORMModel):
    current_step: str
    section_statuses: dict[str, str]
    onboarding_status: str
    started_at: datetime
    completed_at: datetime | None


class SectionCompletion(BaseModel):
    id: str
    completion: int
    weight: int


class CompletionRead(BaseModel):
    overall_completion: int
    sections: list[SectionCompletion]
    important_missing_fields: list[str]


class DemoContext(BaseModel):
    founder: FounderRead
    organization: OrganizationRead
    funding_intent: FundingIntentRead
    details: BusinessDetailsRead
    interests: InterestsRead
    onboarding: OnboardingRead
    completion: CompletionRead
