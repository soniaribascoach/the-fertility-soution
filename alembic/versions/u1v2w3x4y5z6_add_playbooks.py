"""add the playbook library and seed a first pass

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-08-03 00:00:00.000000

Part 4 of Sonia's Operating Manual v1.0, as a table. One playbook is retrieved
per turn and its examples become that turn's few-shots.

This is what CELEBRATE, ACKNOWLEDGE and HONEST_DECLINE have never had. They run
with no few-shots today because `few_shots/` contains nothing resembling them:
every transcript there is a qualification conversation ending in a booking link,
which is the worst possible thing to demonstrate for a pregnancy announcement.

The seed is a FIRST PASS. Entries sourced `DRAFT - needs Sonia` were written
because no prior art exists anywhere in the project; entries sourced
`manual v1.0` are her own approved replies, quoted from Part 1 section 8 and
Part 2A section 4. She replaces the drafts with real edited conversations, which
is the growth path she asked for.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playbooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False, unique=True, index=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="", index=True),
        sa.Column("intents", sa.Text(), nullable=False, server_default=""),
        sa.Column("stages", sa.Text(), nullable=False, server_default=""),
        sa.Column("triggers", sa.Text(), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
        sa.Column("situation", sa.Text(), nullable=False, server_default=""),
        sa.Column("goal", sa.Text(), nullable=False, server_default=""),
        sa.Column("emotional_outcome", sa.Text(), nullable=False, server_default=""),
        sa.Column("communication_priorities", sa.Text(), nullable=False, server_default=""),
        sa.Column("mistakes_to_avoid", sa.Text(), nullable=False, server_default=""),
        sa.Column("examples", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("conversation_state", sa.Text(), nullable=False, server_default=""),
        sa.Column("success_criteria", sa.Text(), nullable=False, server_default=""),
        sa.Column("information_that_matters", sa.Text(), nullable=False, server_default=""),
        sa.Column("decision_outcome", sa.Text(), nullable=False, server_default=""),
        sa.Column("why_this_works", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Imported here so the migration seeds exactly what the app will retrieve.
    import json

    from app.services.brain.playbook_seed import SEED

    conn = op.get_bind()
    insert = sa.text(
        "INSERT INTO playbooks (slug, title, mode, intents, stages, triggers, language, "
        "situation, goal, emotional_outcome, communication_priorities, mistakes_to_avoid, "
        "examples, conversation_state, success_criteria, information_that_matters, "
        "decision_outcome, why_this_works, source, active) "
        "VALUES (:slug, :title, :mode, :intents, :stages, :triggers, :language, "
        ":situation, :goal, :emotional_outcome, :communication_priorities, :mistakes_to_avoid, "
        ":examples, :conversation_state, :success_criteria, :information_that_matters, "
        ":decision_outcome, :why_this_works, :source, true)"
    )
    for p in SEED:
        conn.execute(insert, {
            "slug": p.slug,
            "title": p.title,
            "mode": p.mode or "",
            "intents": "\n".join(p.intents),
            "stages": "\n".join(p.stages),
            "triggers": "\n".join(p.triggers),
            "language": p.language,
            "situation": p.situation,
            "goal": p.goal,
            "emotional_outcome": p.emotional_outcome,
            "communication_priorities": "\n".join(p.communication_priorities),
            "mistakes_to_avoid": "\n".join(p.mistakes_to_avoid),
            "examples": json.dumps(p.examples),
            "conversation_state": p.conversation_state,
            "success_criteria": p.success_criteria,
            "information_that_matters": p.information_that_matters,
            "decision_outcome": p.decision_outcome,
            "why_this_works": p.why_this_works,
            "source": p.source,
        })


def downgrade() -> None:
    op.drop_table("playbooks")
