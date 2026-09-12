"""reconcile the knowledge base with Operating Manual v2.1

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-09-12 00:00:02.000000

`v2w3x4y5z6a7` fixed the numbers. This fixes the prose, which was still v1.0 and was still the only
thing the brain could read. Client review points 4, 5, 6, 14 and 16.

4. Positioning. `kb_about` carried the v1.0 approved explanation, the one whose every phrase Sonia
   flagged: optimize from every possible angle, whole-body approach, full picture. v2.1 §5.1 and §C
   replace it, and add the value explanation, which is the part that actually separates her from
   another coach: not more information, but personalization, prioritization, implementation and
   accountability.

5. The consultation. `kb_program` said the team "take a full history", which is the medical intake
   framing v2.1 §5.2 rules out. It is a fit and strategy conversation. The work description also
   leaned on "the complete picture", which §C rules out for the same reason as "full picture".

6. Pregnancy. The Pregnancy Solution was in no key at all, which is why a newly pregnant woman was
   told coaching through pregnancy is not something Sonia does. It goes into `kb_program`, into the
   provides list in `kb_boundaries`, and into `kb_faq`.

14. Medical boundaries. `kb_faq` refused lab interpretation because it "requires the complete
    picture", the wording that implies a fuller review would produce an answer. Hormone dosing
    including DHEA, and any promise to raise or fix AMH, are named in the does-not-provide list.

16. Spanish. Both `kb_about` and `kb_faq` said Sonia works "in English and Spanish" with no mention
    that the materials are English only, which is the disclosure v2.1 §L requires before booking.

Fragment replacement rather than whole-value, matching `v2w3x4y5z6a7`: an admin who has edited one
of these blocks in /admin/config keeps their edit, and only the sentence named here moves.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "w3x4y5z6a7b8"
down_revision: Union[str, None] = "v2w3x4y5z6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PREGNANCY = (
    "The Pregnancy Solution is the pregnancy counterpart to The Fertility Solution, for women who "
    "are already pregnant. It is an 18 module program covering pregnancy education, with weekly "
    "pregnancy group coaching and a significant private coaching component. Private coaching is "
    "central to it, because every pregnancy is different and I meet each woman where she is in "
    "hers. The purpose is to help her experience pregnancy as positively, confidently, radiantly "
    "and powerfully as possible, while supporting her health and creating the healthiest possible "
    "environment for her developing baby."
)

# (key, old fragment, new fragment)
_FRAGMENTS = [
    # 4 and 16: positioning and the language disclosure.
    (
        "kb_about",
        "I help women and couples optimize fertility from every possible angle through a "
        "personalized, research-backed, whole-body approach, working alongside medical care rather "
        "than instead of it.",
        "Fertility does not exist in isolation, so I look at the environment in which fertility is "
        "happening and work with the whole woman or couple, including the male partner. Depending "
        "on the person that may include nutrition, metabolic health, inflammation, hormones, the "
        "nervous system, sleep, environment, mitochondrial health, egg and sperm health, timing, "
        "stress, gut health and preparation alongside fertility treatment. I work alongside "
        "medical care rather than instead of it.\n"
        "My value is not simply giving people more information. Many of the women who come to me "
        "already know a lot: they take supplements, they eat well, some already work with an "
        "acupuncturist or a functional doctor. What I do is help them personalize and prioritize "
        "what matters for them, connect the pieces, implement the right actions consistently and "
        "have accountability and close support, so they are not blindly doing 100 things and "
        "wondering what actually matters.",
    ),
    (
        "kb_about",
        "I work in English and Spanish, and with clients internationally.",
        "I work with clients internationally. I can personally coach in English or Spanish, and "
        "the program materials are in English only.",
    ),
    # 5: the consultation is a fit and strategy conversation.
    (
        "kb_program",
        "It starts with a free consultation with my team, who take a full history and decide "
        "honestly whether I can help.",
        "It starts with a free consultation with my team. That call is a fit and strategy "
        "conversation, not a medical intake: it is where we work out honestly whether I can help "
        "and what the right next step would be.",
    ),
    (
        "kb_program",
        "From there the work is: understanding the complete picture, identifying what can still be "
        "realistically optimized in that specific case, building a plan around it, and holding the "
        "client accountable to implementing it.",
        "From there the work is: understanding what is actually going on in her case, working out "
        "what matters most and in what order, building a plan around that, and staying with her "
        "while she implements it.",
    ),
    # 6: The Pregnancy Solution.
    (
        "kb_program",
        "I support women trying naturally and women preparing for or recovering from IUI and IVF.",
        "I support women trying naturally and women preparing for or recovering from IUI and IVF.\n"
        + _PREGNANCY,
    ),
    (
        "kb_boundaries",
        "IVF and IUI preparation support, and support for male fertility.",
        "IVF and IUI preparation support, support for male fertility, and pregnancy coaching and "
        "support through The Pregnancy Solution.",
    ),
    # 14: hormone dosing and AMH into the does-not-provide list.
    (
        "kb_boundaries",
        "prescriptions or medication management, surgery or tubal reversal,",
        "prescriptions or medication management, hormone dosing of any kind including DHEA, "
        "surgery or tubal reversal,",
    ),
    (
        "kb_boundaries",
        "lab interpretation, supplement protocols, or emergency medical advice.",
        "lab interpretation, supplement protocols, any promise to raise or fix AMH, or emergency "
        "medical advice.",
    ),
    # 14: the refusal must not imply a fuller review would produce an answer.
    (
        "kb_faq",
        "No. Reading results properly requires the complete picture, and that is part of the "
        "coaching rather than something to do over DM.",
        "No. Reading results properly is part of the coaching and not something to do over DM. "
        "That is about where the work happens. It is not a hint that a longer look would produce a "
        "reading, a diagnosis or a dose.",
    ),
    # 16 and 6: the FAQ answers people actually ask.
    (
        "kb_faq",
        "Yes, I work with clients internationally, in English and Spanish.",
        "Yes, I work with clients internationally. I can personally coach in English or Spanish, "
        "though the program materials are in English only.",
    ),
    (
        "kb_faq",
        "How long is the program?",
        "Do you support women who are already pregnant?\n"
        "Yes. The Pregnancy Solution is the pregnancy counterpart to The Fertility Solution, and "
        "it is where that support happens.\n\n"
        "How long is the program?",
    ),
]


def _replace(key: str, old: str, new: str) -> None:
    op.execute(
        sa.text(
            "UPDATE app_config SET value = REPLACE(value, :old, :new) "
            "WHERE key = :key AND value LIKE :needle"
        ).bindparams(key=key, old=old, new=new, needle=f"%{old}%")
    )


def upgrade() -> None:
    for key, old, new in _FRAGMENTS:
        _replace(key, old, new)


def downgrade() -> None:
    for key, old, new in reversed(_FRAGMENTS):
        _replace(key, new, old)
