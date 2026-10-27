"""Normalized Phase 1 repository index, immutable scans, files and dependencies."""
import sqlalchemy as sa
from alembic import op

revision = "0001_repository_index"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("repositories",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(255), nullable=False),
        sa.Column("path", sa.String(2048), nullable=False, unique=True), sa.Column("ignore_patterns", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("scans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("repository_id", sa.String(36), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        *[sa.Column(name, sa.Integer(), nullable=False) for name in ("total_files", "total_lines", "total_bytes", "skipped_files", "dependency_count")],
        *[sa.Column(name, sa.JSON(), nullable=False) for name in ("languages", "frameworks", "package_managers", "test_frameworks", "warnings")],
        sa.Column("has_docker", sa.Boolean(), nullable=False), sa.Column("has_ci", sa.Boolean(), nullable=False),
        sa.Column("branch", sa.String(255)), sa.Column("commit", sa.String(64)), sa.Column("error", sa.String(1024)))
    op.create_index("ix_scans_repository_id", "scans", ["repository_id"])
    op.create_index("ix_scans_repo_created", "scans", ["repository_id", "created_at"])
    op.create_table("files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(2048), nullable=False), sa.Column("language", sa.String(64), nullable=False),
        sa.Column("lines", sa.Integer(), nullable=False), sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False), sa.UniqueConstraint("scan_id", "path", name="uq_files_scan_path"))
    op.create_index("ix_files_scan_id", "files", ["scan_id"])
    op.create_index("ix_files_language", "files", ["language"])
    op.create_table("dependencies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("version", sa.String(1024), nullable=False),
        sa.Column("ecosystem", sa.String(64), nullable=False))
    op.create_index("ix_dependencies_scan_id", "dependencies", ["scan_id"])


def downgrade() -> None:
    op.drop_table("dependencies")
    op.drop_table("files")
    op.drop_table("scans")
    op.drop_table("repositories")
