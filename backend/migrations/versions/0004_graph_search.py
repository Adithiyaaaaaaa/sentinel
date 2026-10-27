"""Persist bounded repository graphs and versioned local entity vectors."""

import sqlalchemy as sa
from alembic import op

revision = "0004_graph_search"
down_revision = "0003_local_reasoning"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("scans", sa.Column("graph_data", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table(
        "embedding_indexes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("model_digest", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *[sa.Column(n, sa.Integer(), nullable=False) for n in ("total", "indexed", "skipped", "dimensions")],
        sa.Column("error", sa.String(512)),
    )
    op.create_index("ix_embedding_indexes_scan_id", "embedding_indexes", ["scan_id"])
    op.create_table(
        "entity_embeddings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "index_id",
            sa.String(36),
            sa.ForeignKey("embedding_indexes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_key", sa.String(64), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.UniqueConstraint("index_id", "entity_key", name="uq_embedding_entity"),
    )
    op.create_index("ix_entity_embeddings_index_id", "entity_embeddings", ["index_id"])


def downgrade():
    op.drop_table("entity_embeddings")
    op.drop_table("embedding_indexes")
    with op.batch_alter_table("scans") as batch:
        batch.drop_column("graph_data")
