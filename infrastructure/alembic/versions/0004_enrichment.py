"""Staged enrichment jobs and provider usage.

Revision ID: 0004_enrichment
Revises: 0003_explorer
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_enrichment"
down_revision = "0003_explorer"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("source_documents") as batch:
        batch.alter_column("source_id", existing_type=sa.Uuid(), nullable=True)
    op.create_table(
        "enrichment_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), sa.ForeignKey("funding_programs.id"), nullable=False),
        sa.Column("retry_of_id", sa.Uuid(), sa.ForeignKey("enrichment_jobs.id")),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "running", "succeeded", "failed", name="jobstatus", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("windmill_job_id", sa.Uuid(), unique=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("source_documents.id")),
        sa.Column("extracted_fields", sa.JSON()),
        sa.Column("proposed_updates", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_enrichment_jobs_opportunity_id", "enrichment_jobs", ["opportunity_id"])
    op.create_index(
        "uq_enrichment_active_opportunity",
        "enrichment_jobs",
        ["opportunity_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "enrichment_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("enrichment_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("response_id", sa.String(150)),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("raw_usage", sa.JSON()),
    )
    op.create_index("ix_enrichment_usage_job_id", "enrichment_usage", ["job_id"])


def downgrade():
    op.drop_index("ix_enrichment_usage_job_id", table_name="enrichment_usage")
    op.drop_table("enrichment_usage")
    op.drop_index("uq_enrichment_active_opportunity", table_name="enrichment_jobs")
    op.drop_index("ix_enrichment_jobs_opportunity_id", table_name="enrichment_jobs")
    op.drop_table("enrichment_jobs")
    with op.batch_alter_table("source_documents") as batch:
        batch.alter_column("source_id", existing_type=sa.Uuid(), nullable=False)
