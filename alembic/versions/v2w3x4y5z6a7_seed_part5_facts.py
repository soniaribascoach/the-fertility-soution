"""seed Part 5 facts and correct the credentials

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-08-03 00:00:00.000000

Part 5 of the Operating Manual is declared the single source of truth for facts
and overrides conflicting references elsewhere. Two things follow.

CORRECTION. The seeded `proof/track_record` entry said "over fifteen years" and
"more than seven hundred families", carried over from `prompt_builder._IDENTITY`.
The manual says sixteen years and 735 babies. Only rows still holding the old
wording are touched, so anything Sonia has already edited is left alone.

PRICING IS SEEDED INACTIVE. The manual says $1,500 to $10,000; the live config
says $1,500 to $14,000. That figure is quoted to real prospects and is not
something to change on a document's say-so, so the entry is inserted with
active=false. It is visible in /sqladmin and one checkbox from live once she
confirms which is current.

Idempotent: an entry is inserted only when no row with that kind and topic
exists, so re-running never duplicates and never overwrites her edits.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v2w3x4y5z6a7"
down_revision: Union[str, None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_TRACK_RECORD = "%fifteen years%"


def upgrade() -> None:
    from app.services.brain.knowledge_part5 import PART5

    conn = op.get_bind()

    for entry in PART5:
        exists = conn.execute(
            sa.text("SELECT 1 FROM knowledge WHERE kind = :kind AND topic = :topic"),
            {"kind": entry.kind, "topic": entry.topic},
        ).fetchone()
        if exists:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO knowledge (kind, topic, content, triggers, language, "
                "source, active) VALUES (:kind, :topic, :content, :triggers, "
                ":language, :source, :active)"
            ),
            {
                "kind": entry.kind,
                "topic": entry.topic,
                "content": entry.content,
                "triggers": "\n".join(entry.triggers),
                "language": entry.language,
                "source": entry.source,
                "active": entry.active,
            },
        )

    conn.execute(
        sa.text(
            "UPDATE knowledge SET content = :content, source = :source "
            "WHERE kind = 'proof' AND topic = 'track_record' AND content LIKE :old"
        ),
        {
            "content": (
                "Sixteen years of this work and 735 babies welcomed, across PCOS, "
                "low AMH, recurrent loss, failed IVF and IUI, unexplained "
                "infertility and male-factor cases."
            ),
            "source": "manual v1.0 Part 1 sections 4 and 16",
            "old": _OLD_TRACK_RECORD,
        },
    )


def downgrade() -> None:
    from app.services.brain.knowledge_part5 import PART5

    conn = op.get_bind()
    for entry in PART5:
        conn.execute(
            sa.text("DELETE FROM knowledge WHERE kind = :kind AND topic = :topic "
                    "AND source LIKE 'manual v1.0%'"),
            {"kind": entry.kind, "topic": entry.topic},
        )
