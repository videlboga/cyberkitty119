"""add note_versions and new note fields, convert tags/links to JSONB

Revision ID: 0005_agent_note_versions
Revises: 0004_pgvector_dim_1536
Create Date: 2025-09-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0005_agent_note_versions'
down_revision = '0004_pgvector_dim_1536'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # notes: add new columns
    with op.batch_alter_table('notes') as batch:
        batch.add_column(sa.Column('raw_link', sa.String(), nullable=True))
        batch.add_column(sa.Column('current_version', sa.Integer(), server_default='0', nullable=False))
        batch.add_column(sa.Column('draft_title', sa.String(), nullable=True))
        batch.add_column(sa.Column('draft_md', sa.Text(), nullable=True))
        batch.add_column(sa.Column('drive_path', sa.String(), nullable=True))
        batch.add_column(sa.Column('sheet_row_id', sa.String(), nullable=True))

    # Convert tags and links to JSONB if backend supports it
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute("CREATE EXTENSION IF NOT EXISTS plpgsql")
        # ensure non-null defaults for conversion
        op.execute("UPDATE notes SET tags = '[]' WHERE tags IS NULL OR tags = ''")
        op.execute("UPDATE notes SET links = '{}' WHERE links IS NULL OR links = ''")
        # convert types
        op.alter_column(
            'notes',
            'tags',
            type_=postgresql.JSONB,
            postgresql_using="CASE WHEN tags IS NULL OR tags = '' THEN '[]'::jsonb ELSE tags::jsonb END",
        )
        op.alter_column(
            'notes',
            'links',
            type_=postgresql.JSONB,
            postgresql_using="CASE WHEN links IS NULL OR links = '' THEN '{}'::jsonb ELSE links::jsonb END",
        )
        # add meta JSONB
        with op.batch_alter_table('notes') as batch:
            batch.add_column(
                sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb"))
            )
        # set default status and backfill
        op.execute("UPDATE notes SET status = 'ingested' WHERE status = 'new'")
        op.execute("ALTER TABLE notes ALTER COLUMN status SET DEFAULT 'ingested'")
    else:
        # SQLite and others: add meta as Text to keep compatibility
        with op.batch_alter_table('notes') as batch:
            batch.add_column(sa.Column('meta', sa.Text(), nullable=True))

    # create note_versions
    # pick JSONB for meta on PG, Text elsewhere
    meta_type = postgresql.JSONB if conn.dialect.name == 'postgresql' else sa.Text()
    op.create_table(
        'note_versions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('note_id', sa.Integer(), sa.ForeignKey('notes.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('markdown', sa.Text(), nullable=False),
        sa.Column('meta', meta_type, nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_note_versions_note_id', 'note_versions', ['note_id', 'version'])


def downgrade() -> None:
    op.drop_index('idx_note_versions_note_id', table_name='note_versions')
    op.drop_table('note_versions')

    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        # optional: revert status default or convert jsonb back to text — skip for safety
        pass

    with op.batch_alter_table('notes') as batch:
        for col in ['raw_link', 'current_version', 'draft_title', 'draft_md', 'meta', 'drive_path', 'sheet_row_id']:
            try:
                batch.drop_column(col)
            except Exception:
                # best-effort on partial states
                pass
