from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from backend.models import FundingType, JobStatus, ReviewStatus, RoundStatus, SourceKind


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    base_url: HttpUrl
    kind: SourceKind
    resource_type: (
        Literal["specific_call", "financing_program", "funding_directory", "grantmaker_programs", "procurement_portal"]
        | None
    ) = None
    active: bool = True
    notes: str | None = None
    allowed_domains: list[str] | None = None
    topics: list[str] | None = None


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: HttpUrl | None = None
    kind: SourceKind | None = None
    resource_type: (
        Literal["specific_call", "financing_program", "funding_directory", "grantmaker_programs", "procurement_portal"]
        | None
    ) = None
    active: bool | None = None
    notes: str | None = None
    allowed_domains: list[str] | None = None
    topics: list[str] | None = None


class SourceRead(ORMModel):
    id: UUID
    name: str
    base_url: str
    kind: SourceKind
    resource_type: str | None
    active: bool
    notes: str | None
    registry_key: str | None
    allowed_domains: list[str] | None
    topics: list[str] | None
    created_at: datetime
    updated_at: datetime


class RoundCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    status: RoundStatus = RoundStatus.unknown
    opens_at: datetime | None = None
    deadline: datetime | None = None
    application_url: HttpUrl | None = None


class RoundRead(ORMModel):
    id: UUID
    name: str
    status: RoundStatus
    opens_at: datetime | None
    deadline: datetime | None
    application_url: str | None


class RuleCreate(BaseModel):
    criterion: str = Field(min_length=1, max_length=100)
    requirement: str = Field(min_length=1)
    document_id: UUID | None = None
    source_url: HttpUrl | None = None

    @model_validator(mode="after")
    def require_provenance(self):
        if self.document_id is None and self.source_url is None:
            raise ValueError("eligibility rule requires a document_id or source_url")
        return self


class RuleRead(ORMModel):
    id: UUID
    criterion: str
    requirement: str
    document_id: UUID | None
    source_url: str | None


class OpportunityCreate(BaseModel):
    source_id: UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    funding_type: FundingType
    summary: str | None = None
    url: HttpUrl | None = None
    geography: str | None = None
    organization_types: list[Literal["business", "nonprofit", "individual", "cooperative"]] = Field(
        default_factory=list
    )
    amount_min: int | None = Field(default=None, ge=0)
    amount_max: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    rounds: list[RoundCreate] = Field(default_factory=list)
    eligibility_rules: list[RuleCreate] = Field(default_factory=list)


class OpportunityRead(ORMModel):
    id: UUID
    source_id: UUID | None
    title: str
    funding_type: FundingType
    summary: str | None
    details: dict | None
    url: str | None
    geography: str | None
    organization_types: list[str]
    amount_min: int | None
    amount_max: int | None
    currency: str | None
    review_status: ReviewStatus
    verification_status: ReviewStatus
    application_status: RoundStatus
    publication_status: Literal["published", "unpublished"]
    verified_at: datetime | None
    published_at: datetime | None
    rounds: list[RoundRead]
    eligibility_rules: list[RuleRead]
    created_at: datetime
    updated_at: datetime


class OpportunityUpdate(BaseModel):
    source_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    funding_type: FundingType | None = None
    summary: str | None = None
    details: dict | None = None
    url: HttpUrl | None = None
    geography: str | None = None
    organization_types: list[Literal["business", "nonprofit", "individual", "cooperative"]] | None = None
    amount_min: int | None = Field(default=None, ge=0)
    amount_max: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    rounds: list[RoundCreate] | None = None
    eligibility_rules: list[RuleCreate] | None = None

    @model_validator(mode="after")
    def require_non_null_core_fields(self):
        for name in ("title", "funding_type", "organization_types", "rounds", "eligibility_rules"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class VersionRead(ORMModel):
    id: UUID
    program_id: UUID
    snapshot: dict
    change_note: str | None
    created_at: datetime


class JobCreate(BaseModel):
    source_id: UUID | None = None
    metadata: dict | None = None
    mode: str | None = None
    query: str | None = None
    limit: int = Field(default=8, ge=1, le=30)

    @model_validator(mode="after")
    def validate_discovery_request(self):
        if self.mode is not None:
            if self.mode not in ("open", "trusted") or not self.query or not self.query.strip():
                raise ValueError("Discovery job requires mode open or trusted and a query")
            if self.mode == "trusted" and self.source_id is None:
                raise ValueError("Trusted discovery requires a source_id")
        elif self.source_id is None:
            raise ValueError("A source_id or discovery mode is required")
        return self


class DiscoveryRunCreate(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    limit: int | None = Field(default=None, ge=1, le=30)
    source_id: UUID | None = None

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Describe the opportunities to find")
        return value


class JobRead(ORMModel):
    id: UUID
    source_id: UUID | None
    status: JobStatus
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    job_metadata: dict | None
    created_at: datetime


class EnrichmentJobsCreate(BaseModel):
    opportunity_ids: list[UUID] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.opportunity_ids)) != len(self.opportunity_ids):
            raise ValueError("opportunity_ids must be unique")
        return self


class EnrichmentJobRead(ORMModel):
    id: UUID
    opportunity_id: UUID
    retry_of_id: UUID | None
    status: JobStatus
    display_status: str
    stage: str
    windmill_job_id: UUID | None
    document_id: UUID | None
    extracted_fields: dict | None
    proposed_updates: dict | None
    proposal: dict | None
    review_decision: str | None
    reviewed_at: datetime | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class EnrichmentFailure(BaseModel):
    error: str = Field(min_length=1, max_length=4000)


class EnrichmentReview(BaseModel):
    accepted_fields: list[str] = Field(default_factory=list)
    edited_fields: dict = Field(default_factory=dict)


class EnrichmentEvidence(BaseModel):
    field: str
    source_url: HttpUrl
    excerpt: str = Field(min_length=1, max_length=1000)
    confidence: str | None = None


class EnrichmentRule(BaseModel):
    criterion: str = Field(min_length=1, max_length=100)
    requirement: str = Field(min_length=1)
    source_url: HttpUrl


class EnrichmentRound(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    status: RoundStatus = RoundStatus.unknown
    opens_at: datetime | None = None
    deadline: datetime | None = None
    application_url: HttpUrl | None = None


class EnrichmentExtraction(BaseModel):
    title: str | None = None
    funding_type: FundingType | None = None
    summary: str | None = None
    funding_organization: str | None = None
    eligible_applicants: str | None = None
    description: str | None = None
    objectives: list[str] | None = None
    sectors: list[str] | None = None
    geography: str | None = None
    organization_types: list[str] | None = None
    amount_min: int | None = None
    amount_max: int | None = None
    currency: str | None = None
    funding_conditions: list[str] | None = None
    required_documents: list[str] | None = None
    application_steps: list[str] | None = None
    application_url: HttpUrl | None = None
    official_source_url: HttpUrl | None = None
    application_status: RoundStatus | None = None
    opens_at: datetime | None = None
    deadline: datetime | None = None
    rounds: list[EnrichmentRound] | None = None
    eligibility_rules: list[EnrichmentRule] | None = None
    evidence: list[EnrichmentEvidence] = Field(default_factory=list)


class CandidateRead(ORMModel):
    id: UUID
    source_id: UUID | None
    job_id: UUID | None
    canonical_url: str | None
    url: str
    title: str | None
    status: str
    extracted_data: dict | None
    program_id: UUID | None
    created_at: datetime
    updated_at: datetime


class CandidatePromote(BaseModel):
    funding_type: FundingType
    title: str | None = Field(default=None, min_length=1, max_length=300)


class UsageSummary(BaseModel):
    period_start: datetime
    response_count: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    web_search_calls: int
    estimated_cost_usd: float | None
    cost_is_partial: bool


class UsageRead(ORMModel):
    id: UUID
    job_id: UUID
    provider: str
    model: str
    operation: str
    response_id: str | None
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    web_search_calls: int
    estimated_cost_usd: float | None
    rate_snapshot: dict | None
    created_at: datetime


class ReviewDecision(BaseModel):
    note: str | None = None


class ReviewRead(ORMModel):
    id: UUID
    program_id: UUID
    status: ReviewStatus
    note: str | None
    reviewed_at: datetime | None
    program: OpportunityRead


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=50)
    country: str = Field(min_length=2, max_length=2)
    region: str | None = None
    website: HttpUrl | None = None
    description: str | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: str | None = Field(default=None, min_length=1, max_length=50)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = None
    website: HttpUrl | None = None
    description: str | None = None


class OrganizationRead(ORMModel):
    id: UUID
    name: str
    kind: str
    country: str
    region: str | None
    website: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
