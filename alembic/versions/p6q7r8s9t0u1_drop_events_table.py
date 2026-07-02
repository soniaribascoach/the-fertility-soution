"""drop the orphan events table (unused scaffolding, never wired up)

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-07-02 00:00:00.000000

The Event model / create_event repo / EventAdmin were never used (no callers).
No migration ever created the table; it only appeared via dev's create_all.
Drop it if present so migrated DBs are clean.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS events")


def downgrade() -> None:
    # Intentionally a no-op: the table was unused scaffolding and is not restored.
    pass
