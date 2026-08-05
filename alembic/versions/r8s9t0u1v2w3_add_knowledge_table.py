"""add knowledge table and seed it from existing approved content

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-07-29 00:00:00.000000

The seed comes from content that already exists in this project:

* `app_config.prompt_pattern_responses` - 11 situation reframes in Sonia's own
  voice, written by the client in April 2026 and read by nothing since Gen 2.
  Parsed here into individual retrievable entries.
* `app/services/brain/knowledge_seed.py` - positioning, boundaries, objection
  handling and proof lifted from the Gen 2 system prompt and scripts.

`prompt_about` and `prompt_services` are deliberately NOT seeded: they are
generic third-person agency copy listing services she does not offer, which is
the "could describe almost any wellness coach" problem this table exists to fix.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r8s9t0u1v2w3"
down_revision: Union[str, None] = "q7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    """`main.py` runs `create_all` at startup, so on a dev database these tables
    can already exist before the migration runs. Creating one twice is a hard
    error that strands the whole upgrade - which is how a database ends up five
    migrations behind with an empty knowledge table and the old brain live."""
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _table_exists("knowledge"):
        op.create_table(
            "knowledge",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(length=32), nullable=False, index=True),
            sa.Column("topic", sa.String(length=80), nullable=False, index=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("triggers", sa.Text(), nullable=False, server_default=""),
            sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
            sa.Column("source", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # Imported here so the migration seeds exactly what the app will retrieve.
    from app.services.brain.knowledge import parse_pattern_responses
    from app.services.brain.knowledge_seed import SEED

    # Seeding is skipped when rows already exist, so a re-run cannot
    # duplicate the library or collide with an edit Sonia has made.
    if op.get_bind().execute(
            sa.text("SELECT count(*) FROM knowledge")).scalar():
        return  # already seeded

    conn = op.get_bind()
    entries = list(SEED)

    # The client's own reframes, finally wired to something.
    row = conn.execute(
        sa.text("SELECT value FROM app_config WHERE key = 'prompt_pattern_responses'")
    ).fetchone()
    if row and row[0]:
        entries.extend(parse_pattern_responses(row[0]))

    insert = sa.text(
        "INSERT INTO knowledge (kind, topic, content, triggers, language, source, active) "
        "VALUES (:kind, :topic, :content, :triggers, :language, :source, true)"
    )
    for entry in entries:
        conn.execute(insert.bindparams(
            kind=entry.kind,
            topic=entry.topic,
            content=entry.content,
            triggers="\n".join(entry.triggers),
            language=entry.language,
            source=entry.source,
        ))


def downgrade() -> None:
    op.drop_table("knowledge")
