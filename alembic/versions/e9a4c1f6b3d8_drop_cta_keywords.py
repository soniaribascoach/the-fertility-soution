"""drop the reel keyword list, v4 welcome line

Revision ID: e9a4c1f6b3d8
Revises: d8f3b0e5a2c7
Create Date: 2026-10-09 00:00:01.000000

Manual v4.0 §O: any standalone opening word is a conversation starter, including words nobody has
added to a list. A list the team has to keep current is a welcome that silently stops working the
day a new reel goes out, so `cta_keywords` goes and any one-word first message gets the welcome.

The welcome itself stays in config and moves to the v4 line. The old one asked 2 questions in one
message, which §O rules out.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9a4c1f6b3d8"
down_revision: Union[str, None] = "d8f3b0e5a2c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WELCOME = "I’m so glad you reached out ♡ How long have you been trying to conceive?"
_OLD_WELCOME = (
    "I’m so glad you reached out \U0001f90d Before I point you in the right direction, "
    "I’d love to understand a little more about your situation. How long have you been "
    "trying to conceive, and what have you already tried so far?"
)


def _set_welcome(value: str) -> None:
    op.execute(
        sa.text(
            "INSERT INTO app_config (key, value) VALUES ('cta_welcome_message', :value) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
        ).bindparams(value=value)
    )


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM app_config WHERE key = 'cta_keywords'"))
    _set_welcome(_WELCOME)


def downgrade() -> None:
    # The keyword list is gone with its row. It comes back empty, which the old code read as off.
    op.execute(
        sa.text(
            "INSERT INTO app_config (key, value) VALUES ('cta_keywords', '') "
            "ON CONFLICT (key) DO NOTHING"
        )
    )
    _set_welcome(_OLD_WELCOME)
