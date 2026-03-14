"""add app_config table

Revision ID: a1b2c3d4e5f6
Revises: 1265147ff331
Create Date: 2026-03-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '1265147ff331'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_config',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint('key'),
    )

    # Seed default rows
    op.execute(
        sa.text(
            "INSERT INTO app_config (key, value) VALUES "
            "('booking_link', ''), "
            "('score_threshold', '70'), "
            "('system_prompt', 'You are a helpful fertility consultant assistant.'), "
            "('hard_nos', ''), "
            "('medical_blocklist', '') "
            "ON CONFLICT (key) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.drop_table('app_config')
