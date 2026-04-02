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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col['name'] for col in inspector.get_columns('conversations')]
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('conversations')]

    # Rename message → content (only if message still exists)
    if 'message' in existing_columns and 'content' not in existing_columns:
        op.alter_column('conversations', 'message', new_column_name='content')

    # Add role and lead_score columns
    if 'role' not in existing_columns:
        op.add_column('conversations', sa.Column('role', sa.String(length=20), nullable=True))
    if 'lead_score' not in existing_columns:
        op.add_column('conversations', sa.Column('lead_score', sa.Integer(), nullable=True))

    # Add composite index on (instagram_user_id, created_at)
    if 'ix_conversations_user_created' not in existing_indexes:
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
