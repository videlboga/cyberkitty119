"""create note-group tables and link table"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import json

# revision identifiers, used by Alembic.
revision = "0008_add_note_group_links"
down_revision = "0007_processing_jobs_queue"
branch_labels = None
depends_on = None


def _normalise_tags(value):
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip().lower() for item in value if item}
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode()
        except Exception:
            return set()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return set()
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            # fallback: comma separated string
            return {part.strip().lower() for part in value.split(",") if part.strip()}
        return _normalise_tags(parsed)
    return set()


def _json_column(conn):
    if conn.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("note_groups"):
        tags_type = _json_column(conn)
        tags_default = sa.text("'[]'::jsonb") if conn.dialect.name == "postgresql" else sa.text("'[]'")
        op.create_table(
            "note_groups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("color", sa.String(), nullable=True),
            sa.Column("tags", tags_type, nullable=True, server_default=tags_default),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), server_onupdate=sa.func.now(), nullable=False),
        )
        op.create_index("ix_note_groups_user_id", "note_groups", ["user_id"])

    if not inspector.has_table("note_group_links"):
        op.create_table(
            "note_group_links",
            sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("group_id", sa.Integer(), sa.ForeignKey("note_groups.id", ondelete="CASCADE"), primary_key=True),
        )
        op.create_unique_constraint(
            "uq_note_group_links_note_group", "note_group_links", ["note_id", "group_id"]
        )

    notes = conn.execute(sa.text("SELECT id, tags FROM notes")).fetchall()
    groups = conn.execute(sa.text("SELECT id, tags FROM note_groups")).fetchall()
    if not notes or not groups:
        return

    note_tag_map = {row.id: _normalise_tags(row.tags) for row in notes}
    unique_links = set()
    for group_row in groups:
        group_tags = _normalise_tags(group_row.tags)
        if not group_tags:
            continue
        for note_id, note_tags in note_tag_map.items():
            if note_tags and group_tags & note_tags:
                unique_links.add((note_id, group_row.id))

    if unique_links:
        link_table = sa.table(
            "note_group_links",
            sa.column("note_id", sa.Integer),
            sa.column("group_id", sa.Integer),
        )
        conn.execute(
            link_table.insert(),
            [{"note_id": note_id, "group_id": group_id} for note_id, group_id in unique_links],
        )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("note_group_links"):
        op.drop_constraint("uq_note_group_links_note_group", "note_group_links", type_="unique")
        op.drop_table("note_group_links")
