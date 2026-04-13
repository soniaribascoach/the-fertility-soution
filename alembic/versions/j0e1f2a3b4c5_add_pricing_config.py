"""Add prompt_pricing config key with Sonia's pricing handling instructions

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-04-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'j0e1f2a3b4c5'
down_revision: Union[str, None] = 'i9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UPDATES = {
    "prompt_pricing": (
        "When a user asks about pricing, costs, or how much the program is:\n\n"
        "First ask — always do this regardless of intent level:\n"
        "Acknowledge the question warmly and positively — never sound evasive or avoid it. "
        "Explain that we offer different programs depending on the level of support and "
        "personalization someone needs, and that pricing is tied to that level of support. "
        "Position the discovery call as the place where we understand their situation, "
        "determine if we can actually help, and recommend the right level of support. "
        "The call is about fit and personalization — not just selling. "
        "Do NOT share a price range on the first ask. "
        "Always bring the conversation back to the value of the call.\n\n"
        "Second ask (they insist on a number) — engage based on intent level:\n"
        "For higher-intent leads: You may share that our programs range from $1,500 to $14,000 "
        "depending on the level of support. Immediately follow with: 'Before recommending "
        "anything specific, we'd first want to understand your situation fully and make sure "
        "we're the right fit for you.' Then use a confident transition toward booking the "
        "discovery call.\n"
        "For lower-intent leads: Continue to redirect to the discovery call. Emphasise "
        "personalisation and fit over specific numbers. Do not share the range yet.\n\n"
        "Tone always: open, grounded, and confident — not defensive, evasive, or "
        "over-explaining. This is a premium, high-touch experience for people who are ready "
        "to invest in themselves. Never justify or apologise for the price. Always bring the "
        "conversation back to the value of personalised support and the discovery call."
    ),
}


def upgrade() -> None:
    for key, value in _UPDATES.items():
        op.execute(
            sa.text(
                "INSERT INTO app_config (key, value) VALUES (:key, :value) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            ).bindparams(key=key, value=value)
        )


def downgrade() -> None:
    for key in _UPDATES:
        op.execute(
            sa.text(
                "UPDATE app_config SET value = '' WHERE key = :key"
            ).bindparams(key=key)
        )
