"""split the masterclass link from the post-booking replay link

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-09-04 00:00:00.000000

Operating Manual v1.0 listed `/watch-replay` under "After Someone Books" and named no link at all
for the free resource offered to everyone else, so one `masterclass_link` key was used for both
stages. A woman who was never going to book was sent the page written for someone who had, which
is client review point 10.

v2.0 §G gives four links and says which stage each belongs to. `masterclass_link` now means
registration, `/register`, which is the one offered freely; `replay_link` is `/watch-replay` and is
only rendered inside the post-booking block.

`apply_link` is seeded because v2.0 §G names it, and it is deliberately referenced by no prompt and
no conversation. The manual gives the URL and never says which stage sends it, and a link the brain
can see is a link it will eventually send.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REPLAY = "https://www.thefertilitysolution.com/watch-replay"
_REGISTER = "https://www.thefertilitysolution.com/register"

_NEW = {
    "replay_link": _REPLAY,
    "apply_link": "https://www.thefertilitysolution.com/apply",
}


def upgrade() -> None:
    for key, value in _NEW.items():
        op.execute(
            sa.text(
                "INSERT INTO app_config (key, value) VALUES (:key, :value) "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(key=key, value=value)
        )

    # The stored value is the replay URL under a key that now means registration, so it is moved
    # rather than left to mean the wrong thing. Only when it is still the seeded value: an admin
    # who has already put a registration URL there has answered this question themselves.
    op.execute(
        sa.text(
            "UPDATE app_config SET value = :register WHERE key = 'masterclass_link' "
            "AND value = :replay"
        ).bindparams(register=_REGISTER, replay=_REPLAY)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE app_config SET value = :replay WHERE key = 'masterclass_link' "
            "AND value = :register"
        ).bindparams(register=_REGISTER, replay=_REPLAY)
    )
    for key in _NEW:
        op.execute(sa.text("DELETE FROM app_config WHERE key = :key").bindparams(key=key))
