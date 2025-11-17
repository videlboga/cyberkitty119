"""Add beta mode tables and columns

Revision ID: 0002_beta_mode_schema
Revises: 0001_initial_schema
Create Date: 2025-06-22
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_beta_mode_schema'
down_revision = '0001_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('beta_enabled', sa.Boolean(), server_default=sa.false(), nullable=False))

    op.create_table(
        'notes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('type_hint', sa.String(), nullable=True),
        sa.Column('type_confidence', sa.Float(), nullable=True, server_default='0'),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('links', sa.Text(), nullable=True),
        sa.Column('drive_file_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='new'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    )
    op.create_index('idx_notes_user_ts', 'notes', ['user_id', 'ts'])

    op.create_table(
        'note_embeddings',
        sa.Column('note_id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('embedding', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['note_id'], ['notes.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )

    op.create_table(
        'reminders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('note_id', sa.Integer(), nullable=True),
        sa.Column('fire_ts', sa.DateTime(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['note_id'], ['notes.id']),
    )

    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )

    op.create_table(
        'google_credentials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('access_token', sa.String(), nullable=False),
        sa.Column('refresh_token', sa.String(), nullable=True),
        sa.Column('expiry', sa.DateTime(), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )


def downgrade():
    op.drop_table('google_credentials')
    op.drop_table('events')
    op.drop_table('reminders')
    op.drop_table('note_embeddings')
    op.drop_index('idx_notes_user_ts', table_name='notes')
    op.drop_table('notes')
    with op.batch_alter_table('users') as batch:
        batch.drop_column('beta_enabled')
