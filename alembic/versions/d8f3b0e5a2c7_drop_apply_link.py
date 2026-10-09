"""drop the application link

Revision ID: d8f3b0e5a2c7
Revises: c7e2a9d4f1b6
Create Date: 2026-10-09 00:00:00.000000

`apply_link` was seeded in `u1v2w3x4y5z6` because v2.0 named the URL, and nothing ever sent it.
Manual v4.0 settles it: no DM stage uses `/apply`, only the Appendix D email does. A link nothing
sends does not belong in the settings page where it looks live.

`price_range_es` needs nothing here. `r8s9t0u1v2w3` already deletes it with the other dead keys.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8f3b0e5a2c7"
down_revision: Union[str, None] = "c7e2a9d4f1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_APPLY = "https://www.thefertilitysolution.com/apply"


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM app_config WHERE key = 'apply_link'"))


def downgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO app_config (key, value) VALUES ('apply_link', :value) "
            "ON CONFLICT (key) DO NOTHING"
        ).bindparams(value=_APPLY)
    )
