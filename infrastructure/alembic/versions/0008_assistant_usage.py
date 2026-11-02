"""Record assistant provider usage independently of profile updates.

Revision ID: 0008_assistant_usage
Revises: 0007_assistant
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_assistant_usage"
down_revision = "0007_assistant"
branch_labels = None
depends_on = None

profile_json = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    op.create_table("assistant_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.Uuid()),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("response_id", sa.String(150)),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("raw_usage", profile_json))
    op.create_index("ix_assistant_usage_organization_id", "assistant_usage", ["organization_id"])


def downgrade():
    op.drop_table("assistant_usage")
