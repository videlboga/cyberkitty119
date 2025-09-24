"""create note_chunks table with pgvector"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '0003_pgvector_note_chunks'
down_revision = '0002_beta_mode_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('DROP TABLE IF EXISTS note_embeddings')
    op.create_table(
        'note_chunks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('note_id', sa.Integer(), sa.ForeignKey('notes.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(256), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), server_onupdate=sa.func.now()),
    )
    op.create_index('ix_note_chunks_user_id', 'note_chunks', ['user_id'])
    op.create_index('ix_note_chunks_note_id', 'note_chunks', ['note_id'])
    op.create_index('ix_note_chunks_user_chunk', 'note_chunks', ['user_id', 'note_id', 'chunk_index'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_note_chunks_user_chunk', table_name='note_chunks')
    op.drop_table('note_chunks')
    op.create_table(
        'note_embeddings',
        sa.Column('note_id', sa.Integer(), sa.ForeignKey('notes.id'), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('embedding', sa.Text(), nullable=False),
    )
