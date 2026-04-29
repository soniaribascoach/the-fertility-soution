"""add pending_messages table

Revision ID: k1e2f3a4b5c6
Revises: j0e1f2a3b4c5
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = "k1e2f3a4b5c6"
down_revision = "j0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instagram_user_id", sa.String(100), nullable=False),
        sa.Column("manychat_contact_id", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_pending_messages_user_processed_received",
        "pending_messages",
        ["instagram_user_id", "processed_at", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pending_messages_user_processed_received",
                  table_name="pending_messages")
    op.drop_table("pending_messages")
