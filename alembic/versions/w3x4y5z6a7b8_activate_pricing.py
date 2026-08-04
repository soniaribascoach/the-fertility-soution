"""activate the pricing fact with the confirmed figure

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-08-04 00:00:00.000000

The previous migration seeded `fact/pricing_range` with active=false, holding
the manual's "$1,500 to $10,000" while the live config said "$1,500 to $14,000",
because a figure quoted to real prospects is not something to change because a
document says so.

The client confirmed on 2026-08-04 that **$1,500 to $14,000 is current**. The
manual's figure (2B.2 section 6) is out of date. So the entry is corrected and
switched on.

Written as an UPDATE plus a conditional INSERT so it works whether or not the
seed migration has already run against this database, and so it does not
resurrect a row someone deliberately deleted.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w3x4y5z6a7b8"
down_revision: Union[str, None] = "v2w3x4y5z6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONTENT = (
    "Programs currently range from approximately $1,500 to $14,000, "
    "depending on the level of support someone needs."
)
_SOURCE = "client confirmed 2026-08-04; supersedes manual v1.0 2B.2 section 6"


def upgrade() -> None:
    conn = op.get_bind()
    updated = conn.execute(
        sa.text(
            "UPDATE knowledge SET content = :content, source = :source, active = true "
            "WHERE kind = 'fact' AND topic = 'pricing_range'"
        ),
        {"content": _CONTENT, "source": _SOURCE},
    ).rowcount

    if not updated:
        conn.execute(
            sa.text(
                "INSERT INTO knowledge (kind, topic, content, triggers, language, "
                "source, active) VALUES ('fact', 'pricing_range', :content, "
                ":triggers, 'en', :source, true)"
            ),
            {
                "content": _CONTENT,
                "source": _SOURCE,
                "triggers": "how.{0,10}much\nprice\ncost\nrange\nballpark",
            },
        )


def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE knowledge SET active = false "
        "WHERE kind = 'fact' AND topic = 'pricing_range'"
    ))
