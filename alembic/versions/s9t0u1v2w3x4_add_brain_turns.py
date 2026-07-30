"""add brain_turns trace table and shadow-mode config

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-07-30 00:00:00.000000

One row per brain turn: the routing decision, the retrieved knowledge, the
uncertainty score and the per-call cost. Previously `TurnResult.action` and
`.violations` were computed and discarded and both LLM calls were blended into a
single cost figure, so "why did the bot say that" was unanswerable from the
database - which made reviewing tone or calibrating the handoff threshold
guesswork.

Also seeds the shadow-mode and threshold knobs so they are tunable from
/sqladmin with no deploy.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s9t0u1v2w3x4"
down_revision: Union[str, None] = "r8s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONFIG = {
    # "1"/"true" runs the routed brain alongside the live one without sending.
    "brain_shadow_enabled": "0",
    # Uncertainty at or above this hands the turn to a person. Lower = safer.
    "uncertainty_threshold": "3",
}


def upgrade() -> None:
    op.create_table(
        "brain_turns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instagram_user_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), index=True),
        sa.Column("brain_version", sa.String(length=16), nullable=False),
        sa.Column("shadow", sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
        sa.Column("lead_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("intent", sa.String(length=48), nullable=False, server_default="", index=True),
        sa.Column("intent_certainty", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("stage", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("mode", sa.String(length=24), nullable=False, server_default="", index=True),
        sa.Column("reason", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("action", sa.String(length=48), nullable=False, server_default=""),
        sa.Column("question_asked", sa.Text(), nullable=False, server_default=""),
        sa.Column("reply", sa.Text(), nullable=False, server_default=""),
        sa.Column("live_reply", sa.Text(), nullable=False, server_default=""),
        sa.Column("trace", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("violations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("uncertainty_score", sa.Integer(), nullable=False,
                  server_default="0", index=True),
        sa.Column("pause", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pause_reason", sa.String(length=48), nullable=False, server_default=""),
        sa.Column("qualified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("usage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("token_cost", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_brain_turns_shadow_created", "brain_turns", ["shadow", "created_at"])

    for key, value in _CONFIG.items():
        op.execute(
            sa.text(
                "INSERT INTO app_config (key, value) VALUES (:key, :value) "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(key=key, value=value)
        )


def downgrade() -> None:
    op.drop_index("ix_brain_turns_shadow_created", table_name="brain_turns")
    op.drop_table("brain_turns")
    keys = ", ".join(f"'{k}'" for k in _CONFIG)
    op.execute(sa.text(f"DELETE FROM app_config WHERE key IN ({keys})"))
