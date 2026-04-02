"""add ai usage columns to conversations

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, tuple] = ('f6a7b8c9d0e1', 'c3d4e5f6a7b8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('token_cost',        sa.Float(),       nullable=True))
    op.add_column('conversations', sa.Column('prompt_tokens',     sa.Integer(),     nullable=True))
    op.add_column('conversations', sa.Column('completion_tokens', sa.Integer(),     nullable=True))
    op.add_column('conversations', sa.Column('ai_model',          sa.String(50),    nullable=True))


def downgrade() -> None:
    op.drop_column('conversations', 'ai_model')
    op.drop_column('conversations', 'completion_tokens')
    op.drop_column('conversations', 'prompt_tokens')
    op.drop_column('conversations', 'token_cost')
