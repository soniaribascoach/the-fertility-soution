"""seed the reel CTA keywords and the welcome they get

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-08-17 00:00:00.000000

Most conversations start as a comment on a reel, so the first message in the transcript is the one
word she was asked to comment. `app/services/cta.py` answers those with the line below and calls no
model at all. The keys are new rather than the v14 names (`phase1_cta_keywords`,
`phase1_opening_message`), which that brain's deletion removed from the table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "t0u1v2w3x4y5"
down_revision: Union[str, None] = "s9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED = {
    "cta_keywords": (
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
    "cta_welcome_message": (
        "I’m so glad you reached out \U0001f90d Before I point you in the right direction, "
        "I’d love to understand a little more about your situation. How long have you been "
        "trying to conceive, and what have you already tried so far?"
    ),
}


def upgrade() -> None:
    for key, value in _SEED.items():
        # Never clobber a value an admin has already set.
        op.execute(
            sa.text(
                "INSERT INTO app_config (key, value) VALUES (:key, :value) "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(key=key, value=value)
        )


def downgrade() -> None:
    for key in _SEED:
        op.execute(sa.text("DELETE FROM app_config WHERE key = :key").bindparams(key=key))
