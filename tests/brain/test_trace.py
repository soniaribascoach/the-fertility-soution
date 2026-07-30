"""Pure tests for the turn trace and shadow isolation (no LLM, no DB).

Before `brain_turns` existed, `TurnResult.action` and `.violations` were computed
and thrown away, so "why did the bot say that" was unanswerable from the
database and calibrating the handoff threshold was guesswork.

The shadow tests matter more than they look: shadow runs the routed brain on a
real lead's state, and if it mutated that state the lead's funnel position would
silently drift while nothing was ever sent to her.
"""
import copy

import pytest

from app.services.brain import TurnResult
from app.services.brain.constants import empty_lead_state
from app.services.brain.turn import merge_facts


def test_turn_result_has_a_trace_defaulting_to_empty():
    # The funnel brain never sets it, so every consumer must tolerate empty.
    r = TurnResult(reply_text="hi", lead_state=empty_lead_state())
    assert r.trace == {}


def test_trace_survives_construction():
    r = TurnResult(reply_text="hi", lead_state=empty_lead_state(),
                   trace={"mode": "QUALIFY", "intent": "new_prospect"})
    assert r.trace["mode"] == "QUALIFY"


# --- merge_facts: the state mutation shadow must not leak ---------------------

def test_verified_facts_are_applied():
    st = empty_lead_state()
    contradictions = merge_facts(st, {"age": 38, "trying_duration": "2 years"})
    assert st["slots"]["age"] == 38
    assert st["flags"]["situation_shared"] is True
    assert contradictions == []


def test_a_contradiction_is_reported_and_the_old_value_kept():
    """'She said 2 years, now she says 6 months' is a person's job, not a
    silent state update - which is what the funnel brain's merge() did."""
    st = empty_lead_state()
    st["slots"]["trying_duration"] = "2 years"
    contradictions = merge_facts(st, {"trying_duration": "6 months"})
    assert contradictions == ["trying_duration"]
    assert st["slots"]["trying_duration"] == "2 years"


def test_restating_the_same_value_is_not_a_contradiction():
    st = empty_lead_state()
    st["slots"]["age"] = 38
    assert merge_facts(st, {"age": 38}) == []


def test_unstable_slots_are_allowed_to_change():
    # Only a few facts should never silently change. Her openness to a paid
    # programme can legitimately move within a conversation.
    st = empty_lead_state()
    st["slots"]["financial_ready"] = False
    assert merge_facts(st, {"financial_ready": True}) == []
    assert st["slots"]["financial_ready"] is True


def test_a_partner_fact_implies_a_partner():
    st = empty_lead_state()
    merge_facts(st, {"partner_can_join": False})
    assert st["slots"]["partner_status"] == "couple"


def test_unknown_slots_are_ignored():
    st = empty_lead_state()
    merge_facts(st, {"not_a_real_slot": "x"})
    assert "not_a_real_slot" not in st["slots"]


def test_deep_copy_isolates_a_shadow_run():
    """Shadow hands the routed brain a deepcopy precisely so this holds. Without
    it, a lead's funnel position would drift from turns never sent to her."""
    live = empty_lead_state()
    live["slots"]["age"] = 38

    shadow_state = copy.deepcopy(live)
    merge_facts(shadow_state, {"trying_duration": "2 years"})
    shadow_state["flags"]["booking_sent"] = True

    assert live["slots"]["trying_duration"] is None
    assert live["flags"]["booking_sent"] is False
    assert live["flags"]["situation_shared"] is False


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
    ("0", False), ("false", False), ("", False), (None, False), ("maybe", False),
])
def test_shadow_flag_parsing(value, expected):
    from app.worker import _flag
    assert _flag({"brain_shadow_enabled": value}, "brain_shadow_enabled") is expected


def test_shadow_flag_missing_key_is_off():
    from app.worker import _flag
    assert _flag({}, "brain_shadow_enabled") is False
