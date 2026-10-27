"""Preserve existing indexes and add versioned AST analysis and finding evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0002_static_analysis"
down_revision = "0001_repository_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("analysis_summary", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table(
        "code_entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("file", sa.String(2048), nullable=False),
        sa.Column("language", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("parent", sa.String(64)),
        *[
            sa.Column(name, sa.JSON(), nullable=False)
            for name in ("dependencies", "callers", "callees", "features")
        ],
        sa.Column("complexity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("scan_id", "key", name="uq_entity_scan_key"),
    )
    op.create_index("ix_code_entities_scan_id", "code_entities", ["scan_id"])
    op.create_table(
        "findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.String(32), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("file", sa.String(2048), nullable=False),
        sa.Column("language", sa.String(64), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("cwe", sa.String(32)),
        sa.Column("owasp", sa.String(32)),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk", sa.Integer(), nullable=False),
        sa.Column("risk_basis", sa.JSON(), nullable=False),
        *[
            sa.Column(name, sa.Text(), nullable=False)
            for name in ("explanation", "impact", "exploitability", "recommendation")
        ],
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scan_id", "fingerprint", name="uq_finding_scan_fingerprint"),
    )
    op.create_index("ix_findings_scan_id", "findings", ["scan_id"])
    op.create_index("ix_findings_severity", "findings", ["severity"])
    op.create_table(
        "finding_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "finding_id", sa.String(36), sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_index("ix_finding_evidence_finding_id", "finding_evidence", ["finding_id"])


def downgrade() -> None:
    op.drop_table("finding_evidence")
    op.drop_table("findings")
    op.drop_table("code_entities")
    with op.batch_alter_table("scans") as batch:
        batch.drop_column("analysis_summary")
