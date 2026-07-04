"""Tests for the resume feature: resume_lead_state (the flag reset applied when
a human re-arms the AI) and the safety gate scanning only the NEW batch — so an
already-handled media link / blocklist phrase can't re-trip a takeover after a
human resumes. Pure except the one marked live."""
import pytest

from app.services.brain import run_turn
from app.services.brain.constants import (
    COUNTER_KEYS,
    FLAG_KEYS,
    SLOT_KEYS,
    Phase,
    empty_lead_state,
    resume_lead_state,
)


def _taken_over_state() -> dict:
    """A lead mid-funnel who hit a terminal takeover."""
    state = empty_lead_state()
    state["phase"] = Phase.TAKEOVER.value
    state["slots"].update({
        "trying_duration": "2 years",
        "age": 34,
        "treatment_path": "ivf",
        "language": "es",
    })
    state["flags"].update({
        "situation_shared": True,
        "explained_role": True,
        "booking_sent": True,
        "handed_off": True,
        "cost_declined": True,
        "last_prompt": "ASK_PRIORITY",
        "oos_reason": "age_over_46",
        "takeover_reason": "cant_afford_engaging",
    })
    state["counters"].update({"price_ask_count": 2, "repeat_count": 2})
    return state


def test_clears_terminal_control_flags():
    resumed = resume_lead_state(_taken_over_state())
    f = resumed["flags"]
    assert f["handed_off"] is False
    assert f["cost_declined"] is False
    assert f["last_prompt"] is None
    assert f["oos_reason"] is None
    assert f["takeover_reason"] is None
    assert resumed["counters"]["repeat_count"] == 0


def test_preserves_slots_and_progress():
    resumed = resume_lead_state(_taken_over_state())
    assert resumed["slots"]["trying_duration"] == "2 years"
    assert resumed["slots"]["age"] == 34
    assert resumed["slots"]["treatment_path"] == "ivf"
    assert resumed["slots"]["language"] == "es"
    assert resumed["flags"]["situation_shared"] is True
    assert resumed["flags"]["explained_role"] is True
    assert resumed["flags"]["booking_sent"] is True
    assert resumed["counters"]["price_ask_count"] == 2
    assert resumed["phase"] == Phase.TAKEOVER.value


def test_idempotent():
    once = resume_lead_state(_taken_over_state())
    twice = resume_lead_state(once)
    assert once == twice


@pytest.mark.parametrize("state", [None, {}, {"slots": {}, "flags": {}}])
def test_handles_fresh_or_partial_state(state):
    resumed = resume_lead_state(state)
    assert set(resumed["slots"]) == set(SLOT_KEYS)
    assert set(resumed["flags"]) == set(FLAG_KEYS)
    assert set(resumed["counters"]) == set(COUNTER_KEYS)
    assert resumed["flags"]["handed_off"] is False


def test_normalizes_schema():
    """Every key exists after resume, even from an older persisted shape."""
    resumed = resume_lead_state({"phase": "PRIORITY", "slots": {"age": 30}})
    assert resumed["phase"] == "PRIORITY"
    assert resumed["slots"]["age"] == 30
    assert set(resumed["flags"]) == set(FLAG_KEYS)


# --- Safety gate scans only the new batch after a resume -----------------------
#
# Human Live-Chat replies are never saved to our history, so after a media/
# blocklist takeover the old gated message is still a TRAILING user message.
# The worker therefore passes the current batch as new_texts; without it the
# lead's very next message would re-trip the gate forever.

_OLD_LINK = "https://instagram.com/reel/abc123"
_NEW_TEXT = "thanks, that video was me! so what do we do next?"


def _history_after_human_reply():
    # user sent a link (takeover), a human replied in Live Chat (not persisted),
    # the human resumed the AI, then the lead sent a normal message.
    return [
        {"role": "user", "content": _OLD_LINK},
        {"role": "user", "content": _NEW_TEXT},
    ]


async def test_media_in_new_batch_still_gates():
    # gate fires before any LLM call, so no client is needed
    r = await run_turn(None, _history_after_human_reply(), {}, None,
                       new_texts=[_OLD_LINK])
    assert r.action == "SAFETY_MEDIA" and r.pause is True


async def test_no_batch_falls_back_to_trailing_texts():
    # sandbox behavior (no batch): the trailing link still gates
    r = await run_turn(None, _history_after_human_reply(), {}, None)
    assert r.action == "SAFETY_MEDIA" and r.pause is True


async def test_old_blocklist_phrase_not_regated_in_new_batch():
    # blocklisted phrase already handled by a human -> clean new batch passes
    # the gate (gate returns None; run_turn then proceeds toward the extractor,
    # which the empty new_texts=[] NOOP short-circuit lets us avoid here)
    cfg = {"medical_blocklist": "clomid dosage"}
    history = [
        {"role": "user", "content": "what clomid dosage should I take?"},
        {"role": "user", "content": "ok thank you!"},
    ]
    r = await run_turn(None, history, cfg, None, new_texts=[])
    assert r.action == "NOOP" and r.pause is False


@pytest.mark.live
async def test_no_retakeover_after_human_resume(openai_client):
    # THE bug scenario: old link in history, clean new batch -> the funnel
    # continues instead of pausing again.
    r = await run_turn(openai_client, _history_after_human_reply(), {}, None,
                       new_texts=[_NEW_TEXT])
    assert r.pause is False
    assert r.action not in ("SAFETY_MEDIA", "HUMAN_TAKEOVER")
    assert r.reply_text
