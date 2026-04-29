"""add user_state table

Revision ID: l2f3a4b5c6d7
Revises: k1e2f3a4b5c6
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = "l2f3a4b5c6d7"
down_revision = "k1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_state",
        sa.Column("instagram_user_id", sa.String(100), primary_key=True),
        sa.Column("is_ai_paused", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pause_reason", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_state")
