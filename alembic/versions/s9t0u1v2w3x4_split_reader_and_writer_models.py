"""split the read model from the write model, and seed the reader on gpt-5-mini

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-08-12 00:00:00.000000

One model used to serve both stages. They want opposite things. Reading is
extraction under load, twenty typed answers about a whole transcript, and the
safety flags a handover depends on are documented degrading in exactly that
condition, so it is worth a model that thinks. Writing is voice, where thinking
buys little and costs the temperature dial, which the GPT-5 family does not
offer at all.

`brain_model` keeps its meaning and its value: it is the writer. `read_model`
is new and seeded at gpt-5-mini. Blank in either falls back to the constant in
`app/services/brain.py`, so an existing install that never had this row still
reads on gpt-5-mini.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "s9t0u1v2w3x4"
down_revision: Union[str, None] = "r8s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED = {
    "read_model": "gpt-5-mini",
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
