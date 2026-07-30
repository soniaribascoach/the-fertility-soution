"""make the routed brain the default

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-07-30 00:00:00.000000

Switches `brain_version` from "funnel" to "routed" so the intent-routing brain
answers by default.

Only rows currently reading "funnel" are moved. A deployment sitting on
"legacy" is doing so deliberately - usually mid-rollback - and must not be
dragged forward by a migration.

Rollback stays a single field in AppConfig with no deploy: set `brain_version`
back to "funnel" or "legacy" in /sqladmin. Both brains remain wired.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t0u1v2w3x4y5"
down_revision: Union[str, None] = "s9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "UPDATE app_config SET value = 'routed' "
        "WHERE key = 'brain_version' AND value = 'funnel'"
    ))
    # A database that somehow never got the key at all still needs one.
    op.execute(sa.text(
        "INSERT INTO app_config (key, value) VALUES ('brain_version', 'routed') "
        "ON CONFLICT (key) DO NOTHING"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE app_config SET value = 'funnel' "
        "WHERE key = 'brain_version' AND value = 'routed'"
    ))
