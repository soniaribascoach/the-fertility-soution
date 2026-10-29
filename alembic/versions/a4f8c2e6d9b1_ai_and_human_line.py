"""AI identity and human request in one message: one handover line that answers both

Revision ID: a4f8c2e6d9b1
Revises: b5d2e8f1a3c7
Create Date: 2026-10-28 00:00:00.000000

Oct 28 email §3: "Are you Sonia or an AI? I want to speak to a human" got only the review
acknowledgment. A handover never calls the writer, so the identity question went unanswered. This
line is the first sentence of the approved AI disclosure followed by the review acknowledgment.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4f8c2e6d9b1"
down_revision: Union[str, None] = "b5d2e8f1a3c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SEED = {
    "handover_message_ai_human": (
        "You're chatting with Sonia's AI assistant right now. Thank you for sharing this with me ♡ "
        "We'll take a closer look so we can give you a thoughtful, personal response."
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
