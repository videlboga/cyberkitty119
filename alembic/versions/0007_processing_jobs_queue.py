"""processing jobs queue table

Revision ID: 0007_processing_jobs_queue
Revises: 0006_user_timezone
Create Date: 2025-10-09 16:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0007_processing_jobs_queue"
down_revision = "0006_user_timezone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=True),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_processing_jobs_user_id", "processing_jobs", ["user_id"])
    op.create_index("ix_processing_jobs_note_id", "processing_jobs", ["note_id"])
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
    op.create_index("ix_processing_jobs_created_at", "processing_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_created_at", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_note_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_user_id", table_name="processing_jobs")
    op.drop_table("processing_jobs")
