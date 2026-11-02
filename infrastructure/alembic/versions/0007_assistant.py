"""Demo assistant conversations, suggestions, and field provenance.

Revision ID: 0007_assistant
Revises: 0006_founder_onboarding
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_assistant"
down_revision = "0006_founder_onboarding"
branch_labels = None
depends_on = None

profile_json = sa.JSON().with_variant(JSONB(), "postgresql")


def common():
    return [sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table("assistant_conversations", *common(),
        sa.Column("founder_id", sa.Uuid(), sa.ForeignKey("founders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), sa.ForeignKey("funding_programs.id", ondelete="SET NULL")),
        sa.Column("mode", sa.String(10), nullable=False))
    op.create_index("ix_assistant_conversations_founder_id", "assistant_conversations", ["founder_id"])
    op.create_index("ix_assistant_conversations_organization_id", "assistant_conversations", ["organization_id"])
    op.create_table("assistant_messages", *common(),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(12), nullable=False), sa.Column("content", sa.Text(), nullable=False),
        sa.Column("target_field", sa.String(60)), sa.Column("request_id", sa.Uuid()),
        sa.UniqueConstraint("conversation_id", "request_id"))
    op.create_index("ix_assistant_messages_conversation_id", "assistant_messages", ["conversation_id"])
    op.create_table("assistant_suggestions", *common(),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource", sa.String(30), nullable=False), sa.Column("field", sa.String(60), nullable=False),
        sa.Column("value", profile_json, nullable=False), sa.Column("base_value", profile_json),
        sa.Column("confidence", sa.String(12), nullable=False), sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False))
    op.create_index("ix_assistant_suggestions_conversation_id", "assistant_suggestions", ["conversation_id"])
    op.create_table("profile_field_provenance", *common(),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.String(60), nullable=False), sa.Column("source", sa.String(20), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("assistant_conversations.id", ondelete="SET NULL")),
        sa.UniqueConstraint("organization_id", "field"))
    op.create_index("ix_profile_field_provenance_organization_id", "profile_field_provenance", ["organization_id"])


def downgrade():
    op.drop_table("profile_field_provenance")
    op.drop_table("assistant_suggestions")
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")
