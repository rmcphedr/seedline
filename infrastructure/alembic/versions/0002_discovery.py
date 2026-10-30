"""Discovery sources, staged URLs, and per-response usage ledger.

Revision ID: 0002_discovery
Revises: 0001_initial
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_discovery"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("funding_sources", sa.Column("registry_key", sa.String(100), nullable=True))
    op.add_column("funding_sources", sa.Column("allowed_domains", sa.JSON(), nullable=True))
    op.add_column("funding_sources", sa.Column("topics", sa.JSON(), nullable=True))
    op.create_index("ix_funding_sources_registry_key", "funding_sources", ["registry_key"], unique=True)

    with op.batch_alter_table("ingestion_jobs") as batch:
        batch.alter_column("source_id", existing_type=sa.Uuid(), nullable=True)

    op.add_column("opportunity_candidates", sa.Column("job_id", sa.Uuid(), nullable=True))
    op.add_column("opportunity_candidates", sa.Column("canonical_url", sa.String(2048), nullable=True))
    with op.batch_alter_table("opportunity_candidates") as batch:
        batch.alter_column("source_id", existing_type=sa.Uuid(), nullable=True)
        batch.create_foreign_key("fk_opportunity_candidates_job_id_ingestion_jobs", "ingestion_jobs", ["job_id"], ["id"])
    op.create_index("ix_opportunity_candidates_canonical_url", "opportunity_candidates", ["canonical_url"], unique=True)
    op.create_index("ix_opportunity_candidates_job_id", "opportunity_candidates", ["job_id"])
    op.create_index("ix_opportunity_candidates_status", "opportunity_candidates", ["status"])

    op.create_table(
        "discovery_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("response_id", sa.String(150), unique=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("web_search_calls", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6)),
        sa.Column("rate_snapshot", sa.JSON()),
        sa.Column("raw_usage", sa.JSON()),
    )
    op.create_index("ix_discovery_usage_job_id", "discovery_usage", ["job_id"])


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM ingestion_jobs WHERE source_id IS NULL")).scalar():
        raise RuntimeError("Cannot downgrade: open discovery jobs have no source")
    if bind.execute(sa.text("SELECT COUNT(*) FROM opportunity_candidates WHERE source_id IS NULL")).scalar():
        raise RuntimeError("Cannot downgrade: candidates have no source")

    op.drop_index("ix_discovery_usage_job_id", table_name="discovery_usage")
    op.drop_table("discovery_usage")
    op.drop_index("ix_opportunity_candidates_status", table_name="opportunity_candidates")
    op.drop_index("ix_opportunity_candidates_job_id", table_name="opportunity_candidates")
    op.drop_index("ix_opportunity_candidates_canonical_url", table_name="opportunity_candidates")
    with op.batch_alter_table("opportunity_candidates") as batch:
        batch.drop_constraint("fk_opportunity_candidates_job_id_ingestion_jobs", type_="foreignkey")
        batch.alter_column("source_id", existing_type=sa.Uuid(), nullable=False)
        batch.drop_column("canonical_url")
        batch.drop_column("job_id")
    with op.batch_alter_table("ingestion_jobs") as batch:
        batch.alter_column("source_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index("ix_funding_sources_registry_key", table_name="funding_sources")
    op.drop_column("funding_sources", "topics")
    op.drop_column("funding_sources", "allowed_domains")
    op.drop_column("funding_sources", "registry_key")
