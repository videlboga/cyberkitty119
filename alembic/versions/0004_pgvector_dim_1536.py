"""increase pgvector dimension to 1536"""

from alembic import op

# revision identifiers, used by Alembic.
revision = '0004_pgvector_dim_1536'
down_revision = '0003_pgvector_note_chunks'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('ALTER TABLE note_chunks ALTER COLUMN embedding TYPE vector(1536)')


def downgrade() -> None:
    op.execute('ALTER TABLE note_chunks ALTER COLUMN embedding TYPE vector(256)')
