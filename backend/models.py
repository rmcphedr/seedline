import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

PROFILE_JSON = JSON().with_variant(JSONB(), "postgresql")


def now() -> datetime:
    return datetime.now(UTC)


class SourceKind(str, enum.Enum):
    website = "website"
    api = "api"
    directory = "directory"


class FundingType(str, enum.Enum):
    grant = "grant"
    loan = "loan"
    investment = "investment"
    procurement = "procurement"
    competition = "competition"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class RoundStatus(str, enum.Enum):
    upcoming = "upcoming"
    open = "open"
    closed = "closed"
    unknown = "unknown"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Timestamped:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)


class FundingSource(Timestamped, Base):
    __tablename__ = "funding_sources"
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    kind: Mapped[SourceKind] = mapped_column(
        Enum(SourceKind, native_enum=False, create_constraint=True), nullable=False
    )
    resource_type: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    registry_key: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    allowed_domains: Mapped[list | None] = mapped_column(JSON)
    topics: Mapped[list | None] = mapped_column(JSON)


class SourceDocument(Timestamped, Base):
    __tablename__ = "source_documents"
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text)
    document_metadata: Mapped[dict | None] = mapped_column(JSON)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (UniqueConstraint("source_id", "url", "content_hash"),)


class OpportunityCandidate(Timestamped, Base):
    __tablename__ = "opportunity_candidates"
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_jobs.id"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_documents.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32), default="unverified", nullable=False, index=True)
    extracted_data: Mapped[dict | None] = mapped_column(JSON)
    program_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funding_programs.id"), index=True)


class FundingProgram(Timestamped, Base):
    __tablename__ = "funding_programs"
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    funding_type: Mapped[FundingType] = mapped_column(
        Enum(FundingType, native_enum=False, create_constraint=True), nullable=False
    )
    summary: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON)
    url: Mapped[str | None] = mapped_column(String(2048))
    geography: Mapped[str | None] = mapped_column(String(200))
    organization_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    amount_min: Mapped[int | None]
    amount_max: Mapped[int | None]
    currency: Mapped[str | None] = mapped_column(String(3))
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, create_constraint=True),
        default=ReviewStatus.pending,
        nullable=False,
        index=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    rounds: Mapped[list["FundingRound"]] = relationship(
        back_populates="program", cascade="all, delete-orphan", lazy="selectin"
    )
    eligibility_rules: Mapped[list["EligibilityRule"]] = relationship(
        back_populates="program", cascade="all, delete-orphan", lazy="selectin"
    )
    __table_args__ = (Index("ix_funding_programs_title", "title"),)

    @property
    def verification_status(self) -> ReviewStatus:
        return self.review_status

    @property
    def publication_status(self) -> str:
        return "published" if self.published_at else "unpublished"

    @property
    def application_status(self) -> RoundStatus:
        statuses = {round_.status for round_ in self.rounds}
        if RoundStatus.open in statuses:
            return RoundStatus.open
        if RoundStatus.upcoming in statuses:
            return RoundStatus.upcoming
        if statuses == {RoundStatus.closed}:
            return RoundStatus.closed
        return RoundStatus.unknown


class FundingRound(Timestamped, Base):
    __tablename__ = "funding_rounds"
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funding_programs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[RoundStatus] = mapped_column(
        Enum(RoundStatus, native_enum=False, create_constraint=True), default=RoundStatus.unknown, nullable=False
    )
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    application_url: Mapped[str | None] = mapped_column(String(2048))
    program: Mapped[FundingProgram] = relationship(back_populates="rounds")


class EligibilityRule(Timestamped, Base):
    __tablename__ = "eligibility_rules"
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funding_programs.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_documents.id"))
    criterion: Mapped[str] = mapped_column(String(100), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    program: Mapped[FundingProgram] = relationship(back_populates="eligibility_rules")


class OpportunityVersion(Timestamped, Base):
    __tablename__ = "opportunity_versions"
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funding_programs.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_documents.id"))
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text)


class IngestionJob(Timestamped, Base):
    __tablename__ = "ingestion_jobs"
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, create_constraint=True), default=JobStatus.queued, nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    job_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)


class EnrichmentJob(Timestamped, Base):
    __tablename__ = "enrichment_jobs"
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funding_programs.id"), nullable=False, index=True)
    retry_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("enrichment_jobs.id"))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, create_constraint=True), default=JobStatus.queued, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), default="dispatch", nullable=False)
    windmill_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), unique=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_documents.id"))
    extracted_fields: Mapped[dict | None] = mapped_column(JSON)
    proposed_updates: Mapped[dict | None] = mapped_column(JSON)
    proposal: Mapped[dict | None] = mapped_column(JSON)
    review_decision: Mapped[str | None] = mapped_column(String(16))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "uq_enrichment_active_opportunity",
            "opportunity_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )

    @property
    def display_status(self) -> str:
        if self.status == JobStatus.failed:
            return "failed"
        if self.status == JobStatus.queued:
            return "queued"
        if self.status == JobStatus.running:
            return "processing"
        return "pending_review" if self.stage == "pending_review" else "completed"


class EnrichmentUsage(Timestamped, Base):
    __tablename__ = "enrichment_usage"
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("enrichment_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    response_id: Mapped[str | None] = mapped_column(String(150))
    prompt_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    raw_usage: Mapped[dict | None] = mapped_column(JSON)


class DiscoveryUsage(Timestamped, Base):
    __tablename__ = "discovery_usage"
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    response_id: Mapped[str | None] = mapped_column(String(150), unique=True)
    input_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    cache_write_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    web_search_calls: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    rate_snapshot: Mapped[dict | None] = mapped_column(JSON)
    raw_usage: Mapped[dict | None] = mapped_column(JSON)


class ReviewQueue(Timestamped, Base):
    __tablename__ = "review_queue"
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funding_programs.id", ondelete="CASCADE"), unique=True)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, create_constraint=True),
        default=ReviewStatus.pending,
        nullable=False,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    program: Mapped[FundingProgram] = relationship(lazy="selectin")


class Organization(Timestamped, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(2048))
    description: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120))
    industry: Mapped[list[str]] = mapped_column(PROFILE_JSON, default=list, nullable=False)
    business_stage: Mapped[str | None] = mapped_column(String(40))
    legal_structure: Mapped[str | None] = mapped_column(String(40))
    incorporation_status: Mapped[str | None] = mapped_column(String(40))
    year_established: Mapped[int | None]
    business_model: Mapped[str | None] = mapped_column(String(20))


class Founder(Timestamped, Base):
    __tablename__ = "founders"
    auth_user_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    demo_kind: Mapped[str | None] = mapped_column(String(20))
    display_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    city: Mapped[str | None] = mapped_column(String(120))
    province: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(2))
    professional_background: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(String(2048))


class OrganizationMembership(Timestamped, Base):
    __tablename__ = "organization_memberships"
    founder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("founders.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str | None] = mapped_column(String(120))
    __table_args__ = (UniqueConstraint("founder_id", "organization_id"),)


class FundingIntent(Timestamped, Base):
    __tablename__ = "funding_intents"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    project_description: Mapped[str | None] = mapped_column(Text)
    funding_purposes: Mapped[list[str]] = mapped_column(PROFILE_JSON, default=list, nullable=False)
    amount_min: Mapped[int | None]
    amount_max: Mapped[int | None]
    amount_unsure: Mapped[bool | None] = mapped_column(Boolean)
    funding_timeline: Mapped[str | None] = mapped_column(String(40))
    preferred_funding_types: Mapped[list[str]] = mapped_column(PROFILE_JSON, default=list, nullable=False)


class BusinessDetails(Timestamped, Base):
    __tablename__ = "business_profile_details"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    employee_count: Mapped[int | None]
    years_in_operation: Mapped[int | None]
    annual_revenue_range: Mapped[str | None] = mapped_column(String(40))
    previous_funding: Mapped[str | None] = mapped_column(String(12))
    previous_funding_details: Mapped[str | None] = mapped_column(Text)
    current_funding_status: Mapped[str | None] = mapped_column(String(40))
    ownership_eligibility: Mapped[list[str] | None] = mapped_column(PROFILE_JSON)


class FounderInterests(Timestamped, Base):
    __tablename__ = "founder_interests"
    founder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("founders.id", ondelete="CASCADE"), unique=True)
    expertise: Mapped[list[str]] = mapped_column(PROFILE_JSON, default=list, nullable=False)
    challenges: Mapped[list[str]] = mapped_column(PROFILE_JSON, default=list, nullable=False)
    support_areas: Mapped[list[str]] = mapped_column(PROFILE_JSON, default=list, nullable=False)
    mentorship_interest: Mapped[bool | None] = mapped_column(Boolean)
    collaboration_interest: Mapped[bool | None] = mapped_column(Boolean)
    connections_opt_in: Mapped[bool | None] = mapped_column(Boolean)


class OnboardingState(Timestamped, Base):
    __tablename__ = "onboarding_states"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    current_step: Mapped[str] = mapped_column(String(40), default="founder_basics", nullable=False)
    section_statuses: Mapped[dict] = mapped_column(PROFILE_JSON, default=dict, nullable=False)
    onboarding_status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DemoSession(Timestamped, Base):
    __tablename__ = "demo_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    founder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("founders.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
