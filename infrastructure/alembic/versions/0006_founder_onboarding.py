"""Founder profiles, business details, onboarding, and local demo sessions.

Revision ID: 0006_founder_onboarding
Revises: 0005_enrichment_review
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_founder_onboarding"
down_revision = "0005_enrichment_review"
branch_labels = None
depends_on = None

profile_json = sa.JSON().with_variant(JSONB(), "postgresql")


def common():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.add_column("organizations", sa.Column("city", sa.String(120)))
    op.add_column("organizations", sa.Column("industry", profile_json, nullable=False, server_default="[]"))
    op.add_column("organizations", sa.Column("business_stage", sa.String(40)))
    op.add_column("organizations", sa.Column("legal_structure", sa.String(40)))
    op.add_column("organizations", sa.Column("incorporation_status", sa.String(40)))
    op.add_column("organizations", sa.Column("year_established", sa.Integer()))
    op.add_column("organizations", sa.Column("business_model", sa.String(20)))

    op.create_table("founders", *common(),
        sa.Column("auth_user_id", sa.String(200), unique=True),
        sa.Column("demo_kind", sa.String(20)),
        sa.Column("display_name", sa.String(200)), sa.Column("email", sa.String(320)),
        sa.Column("city", sa.String(120)), sa.Column("province", sa.String(100)),
        sa.Column("country", sa.String(2)), sa.Column("professional_background", sa.Text()),
        sa.Column("linkedin_url", sa.String(2048)),
    )
    op.create_table("organization_memberships", *common(),
        sa.Column("founder_id", sa.Uuid(), sa.ForeignKey("founders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(120)), sa.UniqueConstraint("founder_id", "organization_id"),
    )
    op.create_index("ix_organization_memberships_founder_id", "organization_memberships", ["founder_id"])
    op.create_index("ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"])
    op.create_table("funding_intents", *common(),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("project_description", sa.Text()),
        sa.Column("funding_purposes", profile_json, nullable=False),
        sa.Column("amount_min", sa.Integer()), sa.Column("amount_max", sa.Integer()),
        sa.Column("amount_unsure", sa.Boolean()), sa.Column("funding_timeline", sa.String(40)),
        sa.Column("preferred_funding_types", profile_json, nullable=False),
    )
    op.create_index("ix_funding_intents_organization_id", "funding_intents", ["organization_id"])
    op.create_table("business_profile_details", *common(),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("employee_count", sa.Integer()), sa.Column("years_in_operation", sa.Integer()),
        sa.Column("annual_revenue_range", sa.String(40)),
        sa.Column("previous_funding", sa.String(12)), sa.Column("previous_funding_details", sa.Text()),
        sa.Column("current_funding_status", sa.String(40)), sa.Column("ownership_eligibility", profile_json),
    )
    op.create_table("founder_interests", *common(),
        sa.Column("founder_id", sa.Uuid(), sa.ForeignKey("founders.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("expertise", profile_json, nullable=False), sa.Column("challenges", profile_json, nullable=False),
        sa.Column("support_areas", profile_json, nullable=False),
        sa.Column("mentorship_interest", sa.Boolean()), sa.Column("collaboration_interest", sa.Boolean()),
        sa.Column("connections_opt_in", sa.Boolean()),
    )
    op.create_table("onboarding_states", *common(),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("current_step", sa.String(40), nullable=False), sa.Column("section_statuses", profile_json, nullable=False),
        sa.Column("onboarding_status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_table("demo_sessions", *common(),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("founder_id", sa.Uuid(), sa.ForeignKey("founders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_demo_sessions_token_hash", "demo_sessions", ["token_hash"], unique=True)
    op.create_index("ix_demo_sessions_founder_id", "demo_sessions", ["founder_id"])
    op.create_index("ix_demo_sessions_organization_id", "demo_sessions", ["organization_id"])


def downgrade():
    op.drop_table("demo_sessions")
    op.drop_table("onboarding_states")
    op.drop_table("founder_interests")
    op.drop_table("business_profile_details")
    op.drop_table("funding_intents")
    op.drop_table("organization_memberships")
    op.drop_table("founders")
    for column in ("business_model", "year_established", "incorporation_status", "legal_structure", "business_stage", "industry", "city"):
        op.drop_column("organizations", column)
