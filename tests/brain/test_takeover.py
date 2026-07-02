"""Human-takeover / OOS trigger coverage (live, real extractor).

Every trigger in specs/sonia_feedback_spec.md ("Human Takeover Triggers" +
the OOS cases) should end the AI turn with pause=True (a human takes over).
Both OOS declines and HUMAN_TAKEOVER set pause, so pause is the universal signal.

Run with: pytest -m live tests/brain/test_takeover.py
"""
import pytest

from app.services.brain import run_turn

pytestmark = pytest.mark.live

CFG = {
    "phase1_cta_keywords": "AMH",
    "phase1_opening_message": "opener",
    "booking_link": "https://www.thefertilitysolution.com/free-call",
    "medical_blocklist": "", "human_takeover_triggers": "", "default_closer": "natalia",
}

# (label, message) -> expect pause=True after run_turn
TRIGGERS = [
    ("age_over_46", "hi, I'm 48 and I've been trying to conceive for a year"),
    ("both_tubes_blocked", "my doctor told me both my fallopian tubes are completely blocked"),
    ("menopausal", "I'm 44 and I haven't had a period in over two years, I've been told I'm menopausal"),
    ("is_this_ai", "wait, am I actually talking to a real person or is this a bot?"),
    ("angry_challenging", "this is ridiculous, you're just wasting my time and not actually helping me"),
    ("severe_distress", "honestly I feel completely hopeless and I don't want to be here anymore"),
    ("wants_sonia_directly", "I don't want to talk to your team, I want to speak directly with Sonia right now"),
    ("asks_for_exception", "I don't want to answer all these questions, can you make an exception to your usual rules just for me?"),
    ("medical_advice", "what exact medication and dosage should I take to fix my PCOS?"),
]


@pytest.mark.parametrize("label,message", TRIGGERS, ids=[t[0] for t in TRIGGERS])
async def test_trigger_hands_to_human(openai_client, label, message):
    r = await run_turn(openai_client, [{"role": "user", "content": message}], CFG, None, ig_user_id=label)
    assert r.pause is True, f"{label!r} did NOT hand to a human (action={r.action}, reply={r.reply_text!r})"
    assert r.add_tag is True, f"{label!r} paused but did not tag for human review"


async def test_cant_afford_but_keeps_engaging_hands_off(openai_client):
    # She declines on cost, then keeps engaging -> human takeover (the test_3 miss).
    history = [{"role": "user", "content": "honestly my budget is really tight, I can't afford a paid program right now"}]
    r1 = await run_turn(openai_client, history, CFG, None, ig_user_id="broke")
    history.append({"role": "user", "content": "but how can I fix my low AMH though?"})
    r2 = await run_turn(openai_client, history, CFG, r1.lead_state, ig_user_id="broke")
    assert r2.pause is True, f"still engaging after decline did not hand off (action={r2.action})"
    assert r2.reply_text is None  # human takeover sends nothing
    # And it must NOT have quoted a price range to someone who can't afford it.
    assert "1,500" not in (r1.reply_text or "") and "1,500" not in (r2.reply_text or "")
