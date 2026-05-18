"""add tables for note qa sessions and messages"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0009_note_qa_sessions"
down_revision = "0008_add_note_group_links"
branch_labels = None
depends_on = None


def _json_column(conn):
    if conn.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    json_type = _json_column(bind)

    if not inspector.has_table("note_qa_sessions"):
        op.create_table(
            "note_qa_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("tags", json_type, nullable=True),
            sa.Column("context_snapshot", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), server_onupdate=sa.func.now(), nullable=False),
            sa.Column("last_message_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("total_messages", sa.Integer(), server_default="0", nullable=False),
            sa.UniqueConstraint("note_id", "user_id", name="uq_note_qa_sessions_note_user"),
        )
        op.create_index("ix_note_qa_sessions_user_id", "note_qa_sessions", ["user_id"])
        op.create_index("ix_note_qa_sessions_note_id", "note_qa_sessions", ["note_id"])

    if not inspector.has_table("note_qa_messages"):
        op.create_table(
            "note_qa_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "session_id",
                sa.Integer(),
                sa.ForeignKey("note_qa_sessions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_note_qa_messages_session_id", "note_qa_messages", ["session_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("note_qa_messages"):
        op.drop_index("ix_note_qa_messages_session_id", table_name="note_qa_messages")
        op.drop_table("note_qa_messages")

    if inspector.has_table("note_qa_sessions"):
        op.drop_index("ix_note_qa_sessions_user_id", table_name="note_qa_sessions")
        op.drop_index("ix_note_qa_sessions_note_id", table_name="note_qa_sessions")
        op.drop_table("note_qa_sessions")
