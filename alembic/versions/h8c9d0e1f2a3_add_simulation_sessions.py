"""add simulation_sessions table

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-04-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'h8c9d0e1f2a3'
down_revision: Union[str, None] = 'g7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'simulation_sessions',
        sa.Column('id',            sa.Integer(),     nullable=False),
        sa.Column('session_id',    sa.String(36),    nullable=False),
        sa.Column('name',          sa.String(200),   nullable=True),
        sa.Column('note',          sa.Text(),        nullable=True),
        sa.Column('first_name',    sa.String(100),   nullable=True),
        sa.Column('message_count', sa.Integer(),     nullable=False, server_default='0'),
        sa.Column('created_at',    sa.DateTime(),    server_default=sa.text('now()')),
        sa.Column('updated_at',    sa.DateTime(),    server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', name='uq_simulation_sessions_session_id'),
    )
    op.create_index('ix_simulation_sessions_created', 'simulation_sessions', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_simulation_sessions_created', table_name='simulation_sessions')
    op.drop_table('simulation_sessions')
