"""add advanced coaching config keys

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_KEYS = [
    "prompt_scoring_rules",
    "prompt_hard_rules",
    "prompt_opening_variants",
    "prompt_qualification_questions",
    "prompt_pattern_responses",
    "prompt_objection_handling",
    "prompt_authority_proof",
    "prompt_cta_transitions",
    "human_takeover_triggers",
]


def upgrade() -> None:
    for key in NEW_KEYS:
        op.execute(
            sa.text(
                f"INSERT INTO app_config (key, value) VALUES ('{key}', '') "
                "ON CONFLICT (key) DO NOTHING"
            )
        )


def downgrade() -> None:
    keys_list = ", ".join(f"'{k}'" for k in NEW_KEYS)
    op.execute(
        sa.text(f"DELETE FROM app_config WHERE key IN ({keys_list})")
    )
