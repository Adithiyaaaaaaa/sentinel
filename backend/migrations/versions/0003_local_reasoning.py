"""Persist local model opinions separately from deterministic evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0003_local_reasoning"
down_revision = "0002_static_analysis"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "finding_id", sa.String(36), sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("model_digest", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("context_summary", sa.JSON(), nullable=False),
        sa.Column("response", sa.JSON()),
        sa.Column("error", sa.String(512)),
    )
    op.create_index("ix_ai_analyses_finding_id", "ai_analyses", ["finding_id"])


def downgrade():
    op.drop_table("ai_analyses")
