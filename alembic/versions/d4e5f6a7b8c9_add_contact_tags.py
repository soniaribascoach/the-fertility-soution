"""add contact_tags column to conversations

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-03-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col['name'] for col in inspector.get_columns('conversations')]
    if 'contact_tags' not in existing_columns:
        op.add_column('conversations', sa.Column('contact_tags', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('conversations', 'contact_tags')
