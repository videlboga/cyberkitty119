"""add user timezone

Revision ID: 0006_user_timezone
Revises: 0005_agent_note_versions
Create Date: 2025-10-02 09:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0006_user_timezone'
down_revision = '0005_agent_note_versions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('timezone', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'timezone')
