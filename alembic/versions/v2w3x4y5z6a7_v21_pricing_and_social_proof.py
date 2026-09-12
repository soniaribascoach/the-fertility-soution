"""current price range, experience and social proof from Operating Manual v2.1

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-09-12 00:00:00.000000

`r8s9t0u1v2w3` seeded the v1.0 facts: $1,500 to $14,000, 16 years, 735 babies. v2.0 §H and the
2 September client review changed all three, v2.1 carried them into Parts 2A and 5, and nothing
carried them into the table the brain actually reads. A prospect was quoted $14,000 in production
on 12 September.

$7,200 is the normal program range. $14,000 was a rare custom scenario and presenting it as the
range scares prospects off, which is the whole reason for the change.

Experience is "nearly 2 decades" rather than a year count. The babies figure is framed as families
Sonia supported going on to welcome 700+ babies, never as a rate and never as something she caused.

Each update is conditional on the seeded value still being in place, matching `u1v2w3x4y5z6`: an
admin who has already edited one of these in /admin/config has answered the question themselves and
must not be overwritten.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "v2w3x4y5z6a7"
down_revision: Union[str, None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_ABOUT_LINE = (
    "I'm Sonia Ribas, a fertility coach with 16 years of experience. I've helped welcome 735 "
    "babies."
)
_NEW_ABOUT_LINE = (
    "I'm Sonia Ribas, a fertility coach. I've spent nearly 2 decades supporting women and couples, "
    "and families I've supported have gone on to welcome 700+ babies."
)

_OLD_PRICING_LINE = (
    "Programs currently range from approximately $1,500 to $14,000, depending on the level of "
    "support."
)
_NEW_PRICING_LINE = (
    "The investment ranges from $1,500 to $7,200 depending on the level of support that's right "
    "for her."
)

# key -> (old value, new value). Whole-value swaps.
_SWAPS = {
    "price_range": ("$1,500 to $14,000", "$1,500 to $7,200"),
    "years_experience": ("16 years", "nearly 2 decades"),
    "babies_welcomed": ("735", "700+"),
}

# key -> (old fragment, new fragment). Substring swaps inside a longer seeded block, so the rest of
# the block is left exactly as it is.
_FRAGMENTS = {
    "kb_about": (_OLD_ABOUT_LINE, _NEW_ABOUT_LINE),
    "kb_pricing": (_OLD_PRICING_LINE, _NEW_PRICING_LINE),
}


def _swap(key: str, old: str, new: str) -> None:
    op.execute(
        sa.text(
            "UPDATE app_config SET value = :new WHERE key = :key AND value = :old"
        ).bindparams(key=key, old=old, new=new)
    )


def _swap_fragment(key: str, old: str, new: str) -> None:
    op.execute(
        sa.text(
            "UPDATE app_config SET value = REPLACE(value, :old, :new) "
            "WHERE key = :key AND value LIKE :needle"
        ).bindparams(key=key, old=old, new=new, needle=f"%{old}%")
    )


def upgrade() -> None:
    for key, (old, new) in _SWAPS.items():
        _swap(key, old, new)
    for key, (old, new) in _FRAGMENTS.items():
        _swap_fragment(key, old, new)


def downgrade() -> None:
    for key, (old, new) in _SWAPS.items():
        _swap(key, new, old)
    for key, (old, new) in _FRAGMENTS.items():
        _swap_fragment(key, new, old)
