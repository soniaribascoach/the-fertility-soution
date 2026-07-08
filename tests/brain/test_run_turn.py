"""End-to-end run_turn tests (Step 7) — real OpenAI, no mocks.

Walks a full qualification funnel turn by turn (as the admin sandbox does,
carrying lead_state forward) and asserts the core guarantees hold end to end.

Run with: pytest -m live tests/brain/test_run_turn.py
"""
import pytest

from app.services.brain import run_turn
from app.services.brain.constants import Action, Phase

pytestmark = pytest.mark.live

BOOKING_URL = "thefertilitysolution.com/free-call"

CFG = {
    "phase1_cta_keywords": "AMH\nBABY\nFERTILITY\nIVF",
    "phase1_opening_message": (
        "I'm so glad you reached out. Before I point you in the right direction, "
        "I'd love to understand a little more about your situation. How long have you "
        "been trying to conceive, and what have you already tried so far?"
    ),
    "booking_link": "https://www.thefertilitysolution.com/free-call",
    "medical_blocklist": "",
    "human_takeover_triggers": "",
    "default_closer": "natalia",
}


async def _say(client, history, lead_state, text):
    history.append({"role": "user", "content": text})
    result = await run_turn(client, history, CFG, lead_state, ig_user_id="test_lead")
    if result.reply_text:
        history.append({"role": "assistant", "content": result.reply_text})
    return result


async def test_phase1_keyword_returns_opener_no_booking(openai_client):
    history = []
    result = await _say(openai_client, history, None, "AMH")
    assert result.action == Action.PHASE1_OPENING.value
    assert BOOKING_URL not in (result.reply_text or "")
    assert result.lead_state["phase"] == Phase.DISCOVERY.value


async def test_full_funnel_books_only_when_qualified(openai_client):
    history = []
    state = None

    # Turn 1: CTA keyword -> opener.
    r = await _say(openai_client, history, state, "FERTILITY")
    state = r.lead_state
    assert BOOKING_URL not in (r.reply_text or "")

    # Scripted lead answers that should drive the funnel to a qualified booking.
    turns = [
        "I'm 38, we've been trying for 2 years and did one round of IVF that didn't work",
        "Honestly it's a 9, it is my top priority right now",
        "Yes, that holistic personalized approach is exactly what I'm looking for",
        "Yes, I understand it's a paid program and I'm open to investing if it's the right fit",
        "I'm doing this on my own as a single mom by choice",
    ]

    booked_turn = None
    for i, msg in enumerate(turns, start=2):
        r = await _say(openai_client, history, state, msg)
        state = r.lead_state
        if r.action == Action.SEND_BOOKING.value:
            booked_turn = i
            assert BOOKING_URL in r.reply_text
            break
        # The booking link must NOT appear before SEND_BOOKING.
        assert BOOKING_URL not in (r.reply_text or ""), f"link leaked on turn {i}: {r.reply_text}"

    assert booked_turn is not None, f"never booked; final phase={state['phase']}, slots={state['slots']}"
    assert state["flags"]["booking_sent"] is True


async def test_one_message_fully_qualified_lead_books(openai_client):
    # Sonia's headline v1.1 bug: her exact test paragraph states every
    # criterion in one message and must get the booking link that same turn.
    history = []
    r = await _say(openai_client, history, None, "FERTILITY")
    state = r.lead_state

    r = await _say(openai_client, history, state, (
        "I'm 38, we've been trying for 18 months, all testing looks normal, "
        "we're trying naturally, pregnancy is a 10 priority, I understand this "
        "is coaching and not medical care, I'm open to a paid program, and my "
        "husband can join the call."
    ))
    assert r.action == Action.SEND_BOOKING.value, (
        f"expected SEND_BOOKING, got {r.action}; slots={r.lead_state['slots']}"
    )
    assert BOOKING_URL in r.reply_text


async def test_price_question_never_leaks_link_or_number(openai_client):
    history = []
    r = await _say(openai_client, history, None, "hi how much does your program cost?")
    assert BOOKING_URL not in (r.reply_text or "")
    assert "$" not in (r.reply_text or "")
    assert r.action == Action.PRICE_DEFLECT.value


async def test_repeated_price_asks_reveal_range_without_reasking(openai_client):
    history = []
    state = None
    # Share enough that discovery is complete first.
    r = await _say(openai_client, history, state, "I'm 38, been trying 2 years, currently doing IVF")
    state = r.lead_state

    # 1st price ask: deflect, no number (validator forbids a figure on deflect).
    r = await _say(openai_client, history, state, "how much does the program cost?")
    state = r.lead_state
    assert r.action == Action.PRICE_DEFLECT_LATE.value
    assert "$" not in (r.reply_text or "")

    # 2nd price ask: reveal the range.
    r = await _say(openai_client, history, state, "ok but seriously, what's the price range?")
    state = r.lead_state
    assert r.action == Action.PRICE_RANGE.value
    assert "1,500" in (r.reply_text or "")


async def test_no_message_repeats_three_times_in_a_row(openai_client):
    # The test_2 bug: the financial question was sent verbatim three times when the
    # lead kept answering with partner info. No reply may repeat 3x consecutively.
    history = []
    state = None
    script = [
        "I'm 34, trying 1 year naturally, my AMH came back low",
        "11 out of 10",
        "yes that's exactly what I want",
        "I'll have to ask my partner",
        "I told you, it's my partner's decision",
        "how do I tell you this?",
    ]
    replies = []
    for msg in script:
        history.append({"role": "user", "content": msg})
        r = await run_turn(openai_client, history, CFG, state, ig_user_id="t2")
        state = r.lead_state
        if r.reply_text:
            history.append({"role": "assistant", "content": r.reply_text})
        replies.append(r.reply_text or "")
    for i in range(len(replies) - 2):
        a, b, c = replies[i], replies[i + 1], replies[i + 2]
        assert not (a and a == b == c), f"reply repeated 3x in a row: {a!r}"


async def test_donor_sperm_solo_lead_told_no_partner_needed(openai_client):
    # Sonia v1.1: a solo/donor lead must be told explicitly that no partner
    # is needed on the call, then asked her stage.
    history = []
    r = await _say(openai_client, history, None, "I'm doing this on my own with donor sperm")
    assert r.action == Action.SOLO_NO_PARTNER_ACK.value, f"got {r.action}"
    text = (r.reply_text or "").lower()
    assert "partner" in text, text
    assert any(w in text for w in ("naturally", "iui", "ivf")), text


async def test_partner_refusal_clarifies_decision_maker_before_link(openai_client):
    # Sonia v1.1: "husband doesn't want to join" must trigger the sole-
    # decision-maker question, never the booking link.
    history = []
    r = await _say(openai_client, history, None, "FERTILITY")
    state = r.lead_state
    for msg in (
        "I'm 36, we've been trying for 3 years, did 2 IUIs that failed",
        "it's a 10, top priority",
        "yes that's exactly the support I'm looking for, and I'm open to a paid program",
    ):
        r = await _say(openai_client, history, state, msg)
        state = r.lead_state
        assert BOOKING_URL not in (r.reply_text or "")

    r = await _say(openai_client, history, state,
                   "I'm married but my husband doesn't want to join the call")
    state = r.lead_state
    assert BOOKING_URL not in (r.reply_text or ""), f"link sent on refusal: {r.reply_text}"

    r = await _say(openai_client, history, state,
                   "I'm the only decision maker, I decide about this myself")
    assert r.action == Action.SEND_BOOKING.value, f"expected booking, got {r.action}"
    assert BOOKING_URL in r.reply_text


async def test_both_tubes_blocked_triggers_takeover(openai_client):
    history = []
    state = None
    r = await _say(openai_client, history, state, "my doctor told me both fallopian tubes are completely blocked")
    state = r.lead_state
    # Either asks to clarify or goes straight to OOS; if it asks, confirm "both".
    if r.action == Action.ASK_BOTH_TUBES.value:
        r = await _say(openai_client, history, state, "both of them are fully blocked")
    assert r.action == Action.OOS_BOTH_TUBES.value
    assert r.pause is True
    assert r.add_tag is True


async def test_one_blocked_tube_acknowledged_no_takeover(openai_client):
    # Sonia v1.1: one blocked tube -> acknowledge the one-vs-both difference
    # and ask the treatment-stage question; no takeover, no generic re-start.
    history = []
    r = await _say(openai_client, history, None, "One of my tubes is blocked")
    assert r.action == Action.ONE_TUBE_ACK.value, f"got {r.action}"
    assert r.pause is False
    text = (r.reply_text or "").lower()
    assert "one" in text, text
    assert any(w in text for w in ("naturally", "iui", "ivf")), text
    assert "?" in text
