"""Pure tests for resume_lead_state — the flag reset applied when a human
re-arms the AI after a takeover (via ManyChat tag automation or the admin
dashboard). No API calls."""
import pytest

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
