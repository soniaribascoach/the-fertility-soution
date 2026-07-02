"""seed brain_version flag and closer config for the qualification-funnel brain

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-06-30 00:00:01.000000

Activates the new deterministic qualification-funnel brain. To roll back to the
legacy monolithic prompt instantly, set app_config key `brain_version` to
`legacy` (editable via /sqladmin -> AppConfig). The closer/URL placeholder keys
are optional overrides; the script registry has safe defaults if they are unset.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED = {
    "brain_version": "funnel",
    "default_closer": "natalia",
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
