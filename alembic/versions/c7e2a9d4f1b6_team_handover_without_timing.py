"""team handover line: no promise about timing

Revision ID: c7e2a9d4f1b6
Revises: w3x4y5z6a7b8
Create Date: 2026-10-08 00:00:00.000000

The seeded `handover_message_team` ended "Someone will come back to you shortly." Nothing in the
system supports that: a paused conversation waits in the dashboard queue and nobody is notified,
which Section E says must not be described as an alert. Sonia's feedback point 6 asks for no
"shortly" unless the timing is real.

Fragment replacement, matching `w3x4y5z6a7b8`: an admin who has rewritten the line in /admin/config
keeps their wording.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7e2a9d4f1b6"
down_revision: Union[str, None] = "w3x4y5z6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD = "Someone will come back to you shortly."
_NEW = "Someone will reply to you here."


def _replace(old: str, new: str) -> None:
    op.execute(
        sa.text(
            "UPDATE app_config SET value = REPLACE(value, :old, :new) "
            "WHERE key = 'handover_message_team' AND value LIKE :needle"
        ).bindparams(old=old, new=new, needle=f"%{old}%")
    )


def upgrade() -> None:
    _replace(_OLD, _NEW)


def downgrade() -> None:
    _replace(_NEW, _OLD)
