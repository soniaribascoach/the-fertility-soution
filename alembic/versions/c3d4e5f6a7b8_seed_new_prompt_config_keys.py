"""seed new prompt config keys and remove old ones

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert new keys with sensible defaults — skip if already present
    op.execute(
        sa.text("""
INSERT INTO app_config (key, value) VALUES
('prompt_about',
'We are a fertility coaching practice dedicated to supporting individuals and couples on their path to parenthood. We combine evidence-informed guidance with deep emotional support, helping clients navigate the physical, emotional, and logistical challenges of their fertility journey. Our coaches are trained to hold space for the full range of experiences — from early exploration to IVF, egg freezing, donor conception, and beyond. We believe every person deserves compassionate, personalised support — not just clinical information.'),

('prompt_services',
'- Free discovery call to understand your situation and goals
- 1-to-1 fertility coaching packages (single sessions and multi-week programmes)
- Emotional support and resilience coaching for IVF cycles
- Mindset and stress-reduction work tailored to fertility challenges
- Support for navigating treatment decisions (IVF, IUI, egg freezing, donor options)
- Guidance for secondary infertility and recurrent loss
- Couples coaching to strengthen communication and shared decision-making
- Post-treatment support whether the outcome is positive or not'),

('prompt_tone',
'- Warm, unhurried, and non-judgmental — never clinical or transactional
- Validate feelings before offering information or next steps
- Use "journey" language: this is their path, not a problem to be fixed
- Ask curious, open questions rather than making assumptions
- Avoid medical jargon; if a clinical term comes up, acknowledge it gently and redirect to what we can help with emotionally and practically
- Never push the booking link — let the conversation earn it
- Example: instead of "We offer IVF coaching", say "Many of our clients come to us right in the middle of an IVF cycle, feeling overwhelmed — we walk alongside them through all of it"'),

('medical_deflection',
'Thank you so much for sharing that with me — it takes courage to ask these questions. Anything to do with medications, dosages, or treatment protocols really needs to come from your doctor or clinic, who know your full picture. What I can do is support you emotionally through whatever you''re navigating, and help you feel more prepared and confident going into those conversations. Would that be helpful?')
ON CONFLICT (key) DO NOTHING
""")
    )

    # Remove keys that no longer exist in the UI
    op.execute(
        sa.text(
            "DELETE FROM app_config WHERE key IN ('system_prompt', 'hard_nos')"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO app_config (key, value) VALUES "
            "('system_prompt', ''), "
            "('hard_nos', '') "
            "ON CONFLICT (key) DO NOTHING"
        )
    )

    op.execute(
        sa.text(
            "DELETE FROM app_config WHERE key IN "
            "('prompt_about', 'prompt_services', 'prompt_tone', 'medical_deflection')"
        )
    )
