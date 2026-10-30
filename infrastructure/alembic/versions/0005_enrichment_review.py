"""Enrichment review proposals and approved structured details.

Revision ID: 0005_enrichment_review
Revises: 0004_enrichment
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_enrichment_review"
down_revision = "0004_enrichment"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("source_documents", sa.Column("document_metadata", sa.JSON()))
    op.add_column("funding_programs", sa.Column("details", sa.JSON()))
    op.add_column("enrichment_jobs", sa.Column("proposal", sa.JSON()))
    op.add_column("enrichment_jobs", sa.Column("review_decision", sa.String(16)))
    op.add_column("enrichment_jobs", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.add_column("enrichment_usage", sa.Column("cost_usd", sa.Numeric(12, 6)))


def downgrade():
    op.drop_column("enrichment_usage", "cost_usd")
    op.drop_column("enrichment_jobs", "reviewed_at")
    op.drop_column("enrichment_jobs", "review_decision")
    op.drop_column("enrichment_jobs", "proposal")
    op.drop_column("funding_programs", "details")
    op.drop_column("source_documents", "document_metadata")
