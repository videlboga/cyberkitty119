"""create processing_jobs table

Revision ID: 20260125_create_processing_jobs
Revises: 
Create Date: 2026-01-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260125_create_processing_jobs'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'processing_jobs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('job_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='queued'),
        sa.Column('payload', sa.JSON, nullable=True),
        sa.Column('progress', sa.Integer, nullable=True),
        sa.Column('attempts', sa.Integer, nullable=False, server_default='0'),
        sa.Column('locked_by', sa.String(64), nullable=True),
        sa.Column('locked_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
        sa.Column('started_at', sa.DateTime, nullable=True),
        sa.Column('finished_at', sa.DateTime, nullable=True),
        sa.Column('error', sa.Text, nullable=True),
    )


def downgrade():
    op.drop_table('processing_jobs')
