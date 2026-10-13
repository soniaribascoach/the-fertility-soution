"""manual v4.1: opt out, age approval and handoff events as recorded states; v4.1 fixed lines

Revision ID: b5d2e8f1a3c7
Revises: f1a7c3e9b2d4
Create Date: 2026-10-12 00:00:00.000000

v4.1 §R makes a handoff, an age booking approval and an opt out three separate states. Until now
the opt out was a pause reason that any release wiped, and age approval was set by the handover
itself. Both become columns on `user_state` that only their own event writes, and every handoff,
release, approval and opt out is written to `lead_events` so it can be shown.

Config: the crisis line loses its commentary and gets a variant for when the team alert failed;
medication and procedure requests get their own clinician line (§J); the approved first general
price reply (§5.3). The fixed welcome goes: a one-word opener is now answered by its own call.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5d2e8f1a3c7"
down_revision: Union[str, None] = "f1a7c3e9b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_HELPLINE = (
    "Please talk to someone tonight. If you’re in the US you can call or text 988, and if you’re "
    "somewhere else findahelpline.com will give you the number where you are. If you feel unsafe "
    "right now, please call your emergency number."
)
_CRISIS_OPENING = (
    "I’m so sorry you’re feeling this way, and I’m really glad you told me. Your safety matters "
    "most right now."
)
_NOT_EMERGENCY = "This inbox isn’t emergency support, so please reach out to one of those now."

_SET = {
    "handover_message_crisis": (
        f"{_CRISIS_OPENING}\n\n{_HELPLINE}\n\n"
        f"I’ve let my team know about your message. {_NOT_EMERGENCY}"
    ),
}

_SEED = {
    "handover_message_crisis_unrouted": f"{_CRISIS_OPENING}\n\n{_HELPLINE}\n\n{_NOT_EMERGENCY}",
    "handover_message_medication": (
        "That’s an important question to get right. Whether to take, stop or change a medication "
        "or a hormone, and how much, is a decision for the doctor prescribing it or managing your "
        "treatment, so please check with them before you change anything ♡"
    ),
    "handover_message_procedure": (
        "That’s a big decision, and whether to have, delay or skip a procedure is one to make with "
        "the doctor managing your care. Please talk it through with them ♡"
    ),
    "price_first_reply": (
        "We have a few different options depending on how much support you’d like. The best way "
        "to work out which fits your needs is a free call with my team, where we can talk through "
        "the options and pricing together. Would you like the booking link?"
    ),
}

_OLD_CRISIS = (
    "I'm reading what you wrote and I'm not going to reply to it with a message.\n\n"
    "Please talk to someone tonight. If you're in the US you can call or text 988, and if "
    "you're somewhere else findahelpline.com will give you the number where you are. If you "
    "feel unsafe right now, please call your emergency number.\n\n"
    "I'm telling my team about this message now and someone will come back to you."
)
_OLD_WELCOME = "I’m so glad you reached out ♡ How long have you been trying to conceive?"


def _upsert(key: str, value: str, overwrite: bool) -> None:
    conflict = "DO UPDATE SET value = EXCLUDED.value" if overwrite else "DO NOTHING"
    op.execute(
        sa.text(
            f"INSERT INTO app_config (key, value) VALUES (:key, :value) ON CONFLICT (key) {conflict}"
        ).bindparams(key=key, value=value)
    )


def upgrade() -> None:
    op.add_column("user_state", sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_state", sa.Column("age_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "lead_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instagram_user_id", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(60), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_lead_events_created", "lead_events", ["created_at"])
    op.create_index("ix_lead_events_user", "lead_events", ["instagram_user_id"])

    for key, value in _SET.items():
        _upsert(key, value, overwrite=True)
    for key, value in _SEED.items():
        _upsert(key, value, overwrite=False)
    op.execute(sa.text("DELETE FROM app_config WHERE key = 'cta_welcome_message'"))


def downgrade() -> None:
    _upsert("cta_welcome_message", _OLD_WELCOME, overwrite=True)
    _upsert("handover_message_crisis", _OLD_CRISIS, overwrite=True)
    for key in _SEED:
        op.execute(sa.text("DELETE FROM app_config WHERE key = :key").bindparams(key=key))

    op.drop_index("ix_lead_events_user", table_name="lead_events")
    op.drop_index("ix_lead_events_created", table_name="lead_events")
    op.drop_table("lead_events")
    op.drop_column("user_state", "age_approved_at")
    op.drop_column("user_state", "opted_out_at")
