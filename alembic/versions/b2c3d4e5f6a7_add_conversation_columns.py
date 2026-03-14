"""add conversation columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename message → content
    op.alter_column('conversations', 'message', new_column_name='content')

    # Add role and lead_score columns
    op.add_column('conversations', sa.Column('role', sa.String(length=20), nullable=True))
    op.add_column('conversations', sa.Column('lead_score', sa.Integer(), nullable=True))

    # Add composite index on (instagram_user_id, created_at)
    op.create_index(
        'ix_conversations_user_created',
        'conversations',
        ['instagram_user_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_conversations_user_created', table_name='conversations')
    op.drop_column('conversations', 'lead_score')
    op.drop_column('conversations', 'role')
    op.alter_column('conversations', 'content', new_column_name='message')
