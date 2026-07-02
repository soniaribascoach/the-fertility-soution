"""Generative-behavior tests (R6): the test_3 fixes + the fallback safety net."""
import pytest

from app.services.brain import run_turn
from app.services.brain.constants import Action
from app.services.brain.directive import TurnDirective
from app.services.brain.validator import validate_generated
from app.services.brain import scripts


# --- Pure: the validator fallback net -----------------------------------------

def test_generated_link_rejected_when_not_allowed():
    d = TurnDirective(mode="FINANCIAL", action=Action.FINANCIAL_CHECK, generate=True,
                      objective="", reference_text="", allow_urls=[], max_chars=400)
    bad = "Sure, book here: https://evil.example.com now"
    assert not validate_generated(d, bad).ok


def test_generated_price_rejected_when_not_allowed():
    d = TurnDirective(mode="DEFLECT_PRICE", action=Action.PRICE_DEFLECT, generate=True,
                      objective="", reference_text="", allow_price_figure=False, max_chars=400)
    assert not validate_generated(d, "It's about $2,000.").ok


def test_generated_missing_required_token_rejected():
    link = scripts.placeholders()["booking_link"]
    d = TurnDirective(mode="BOOK", action=Action.SEND_BOOKING, generate=True,
                      objective="", reference_text="", allow_urls=[link],
                      must_include=[link], max_chars=900)
    assert not validate_generated(d, "Let's book a call soon!").ok
    assert validate_generated(d, f"Book here: {link}").ok


def test_generated_missing_disclaimer_rejected():
    d = TurnDirective(mode="EXPLAIN_ROLE", action=Action.EXPLAIN_ROLE, generate=True,
                      objective="", reference_text="", pinned_text="not a doctor", max_chars=900)
    assert not validate_generated(d, "I use a holistic approach. Interested?").ok
    assert validate_generated(d, "I'm a coach, not a doctor. Interested?").ok


# --- Live: the test_3 behavioral fixes ----------------------------------------

CFG = {
    "phase1_cta_keywords": "AMH",
    "phase1_opening_message": "opener",
    "booking_link": "https://www.thefertilitysolution.com/free-call",
    "medical_blocklist": "", "human_takeover_triggers": "", "default_closer": "natalia",
}


@pytest.mark.live
async def test_emotional_answer_is_acknowledged_not_sales_pitched(openai_client):
    # Reproduce the test_3 moment, carrying state so the priority question is
    # actually asked before the emotional reply lands.
    history, state = [], None

    async def say(msg):
        nonlocal state
        history.append({"role": "user", "content": msg})
        r = await run_turn(openai_client, history, CFG, state, ig_user_id="t3")
        state = r.lead_state
        if r.reply_text:
            history.append({"role": "assistant", "content": r.reply_text})
        return r

    await say("I have low AMH and irregular periods, trying naturally for over a year")
    await say("35")
    r = await say("It's been hard and discouraging.")
    # Must NOT fire the sales re-engagement script at a feeling.
    assert r.action not in (Action.REENGAGE_LOW_PRIORITY.value, Action.LOW_PRIORITY_INFO_GATHERING.value)
    assert "proven track record" not in (r.reply_text or "").lower()
    assert "$" not in (r.reply_text or "") and "http" not in (r.reply_text or "")
