"""add user_identifiers table

Revision ID: 0010_add_user_identifiers
Revises: 0009_note_qa_sessions
Create Date: 2026-03-31 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0010_add_user_identifiers"
down_revision = "0009_note_qa_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("user_identifiers"):
        op.create_table(
            "user_identifiers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("external_id", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("provider", "external_id", name="uq_provider_external_id"),
        )
        op.create_index("ix_user_identifiers_user_id", "user_identifiers", ["user_id"])
        # Migrate existing telegram_id values from users into user_identifiers.
        # Use dialect-specific SQL to avoid syntax issues across sqlite/postgres.
        bind = op.get_bind()
        dialect = bind.dialect.name
        if dialect == "postgresql":
            op.execute(
                sa.text(
                    """
                    INSERT INTO user_identifiers (user_id, provider, external_id, created_at)
                    SELECT id, 'telegram', CAST(telegram_id AS TEXT), now()
                    FROM users
                    WHERE telegram_id IS NOT NULL
                    ON CONFLICT (provider, external_id) DO NOTHING
                    """
                )
            )
        else:
            # sqlite and others: use INSERT OR IGNORE pattern
            op.execute(
                sa.text(
                    """
                    INSERT OR IGNORE INTO user_identifiers (user_id, provider, external_id, created_at)
                    SELECT id, 'telegram', telegram_id, CURRENT_TIMESTAMP
                    FROM users
                    WHERE telegram_id IS NOT NULL
                    """
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("user_identifiers"):
        op.drop_index("ix_user_identifiers_user_id", table_name="user_identifiers")
        op.drop_table("user_identifiers")
