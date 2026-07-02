"""add qualification-funnel state columns to user_state

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-06-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n4o5p6q7r8s9"
down_revision: Union[str, None] = "m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_state", sa.Column("phase", sa.String(40), nullable=True))
    op.add_column("user_state", sa.Column("qualification", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_state", "qualification")
    op.drop_column("user_state", "phase")
