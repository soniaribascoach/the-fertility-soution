"""seed Spanish-language config keys for the bilingual (en/es) brain

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-07-03 00:00:01.000000

The brain now runs the full qualification funnel in English or Spanish (any
other language pauses silently for human review). This seeds the Spanish
config keys with safe defaults; all are editable via /admin/config or
/sqladmin -> AppConfig. Spanish medical-blocklist / takeover-trigger phrases
are deliberately NOT seeded — admins add them to the existing shared lists
(never clobber admin-edited values).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "q7r8s9t0u1v2"
down_revision: Union[str, None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED = {
    # Spanish price range wording ("a" instead of "to"); same figures as price_range.
    "price_range_es": "$1,500 a $14,000",
    # Empty until the client provides one (empty = fall back to medical_deflection).
    "medical_deflection_es": "",
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
