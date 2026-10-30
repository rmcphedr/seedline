"""Verification, publication, and resource classification for explorer.

Revision ID: 0003_explorer
Revises: 0002_discovery
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_explorer"
down_revision = "0002_discovery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("funding_sources", sa.Column("resource_type", sa.String(40), nullable=True))
    op.add_column("funding_programs", sa.Column("organization_types", sa.JSON(), nullable=True))
    op.add_column("funding_programs", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("funding_programs", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE funding_programs SET organization_types = '[]' WHERE organization_types IS NULL")
    op.execute("""
        UPDATE funding_programs SET verified_at = (
            SELECT reviewed_at FROM review_queue
            WHERE review_queue.program_id = funding_programs.id AND review_queue.status = 'approved'
        ) WHERE review_status = 'approved'
    """)
    with op.batch_alter_table("funding_programs") as batch:
        batch.alter_column("organization_types", existing_type=sa.JSON(), nullable=False)
    op.create_index("ix_funding_programs_published_at", "funding_programs", ["published_at"])


def downgrade():
    op.drop_index("ix_funding_programs_published_at", table_name="funding_programs")
    op.drop_column("funding_programs", "published_at")
    op.drop_column("funding_programs", "verified_at")
    op.drop_column("funding_programs", "organization_types")
    op.drop_column("funding_sources", "resource_type")
