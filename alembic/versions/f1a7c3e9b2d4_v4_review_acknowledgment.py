"""review acknowledgment: one line on every handover (manual v4.0)

Revision ID: f1a7c3e9b2d4
Revises: e9a4c1f6b3d8
Create Date: 2026-10-10 00:00:00.000000

v4.0 §F and 2B.2 §13 send the approved review acknowledgment once whenever a conversation goes to
the team, age review included. Until now most handovers sent nothing. `handover_message_review` is
the default line; crisis and urgent medical keep their own, abuse stays silent. The old
`handover_message_team` row is left in place and no longer read.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a7c3e9b2d4"
down_revision: Union[str, None] = "e9a4c1f6b3d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SEED = {
    "handover_message_review": (
        "Thank you for sharing this with me ♡ We'll take a closer look so we can give you a "
        "thoughtful, personal response."
    ),
}


def upgrade() -> None:
    for key, value in _SEED.items():
        op.execute(
            sa.text(
                "INSERT INTO app_config (key, value) VALUES (:key, :value) "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(key=key, value=value)
        )


def downgrade() -> None:
    for key in _SEED:
        op.execute(sa.text("DELETE FROM app_config WHERE key = :key").bindparams(key=key))
