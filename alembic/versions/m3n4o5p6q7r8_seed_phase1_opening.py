"""seed phase1 CTA keywords and opening message

Revision ID: m3n4o5p6q7r8
Revises: l2f3a4b5c6d7
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, None] = "l2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED = {
    "phase1_cta_keywords": (
        "AMH\n"
        "BABY\n"
        "FERTILITY\n"
        "ENERGY\n"
        "IVF\n"
        "HOPE\n"
        "READY\n"
        "TRUTH\n"
        "UNEXPLAINED\n"
        "BLOOD SUGAR\n"
        "SUPPORT"
    ),
    "phase1_opening_message": (
        "I’m so glad you reached out \U0001f90d Before I point you in the right direction, "
        "I’d love to understand a little more about your situation. "
        "How long have you been trying to conceive, and what have you already tried so far?"
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
        op.execute(
            sa.text("DELETE FROM app_config WHERE key = :key").bindparams(key=key)
        )
