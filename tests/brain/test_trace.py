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


# --- Silence has a cost -------------------------------------------------------

def test_hard_and_soft_violations_are_distinguished():
    """Only an unsafe reply is worth going silent over.

    A repeated question or an em-dash is worth far more to the lead than
    nothing at all; a leaked link or an invented lab value is not.
    """
    from app.services.brain.checks import CheckResult, is_hard

    assert is_hard("disallowed_url")
    assert is_hard("invented_number:0.6")
    assert is_hard("medical_advice")
    assert is_hard("echoed_lead:just send me the link")

    assert not is_hard("repeat:How long have you been trying")
    assert not is_hard("em_dash")
    assert not is_hard("markdown")
    assert not is_hard("too_long")
    assert not is_hard("banned_phrase:i hear you")

    r = CheckResult(False, ["repeat:x", "em_dash", "disallowed_url"])
    assert r.hard == ["disallowed_url"]
    assert CheckResult(False, ["repeat:x", "em_dash"]).hard == []


# --- Re-asking a question the opener already asked ----------------------------

_OPENER = ("I'm so glad you reached out. How long have you been trying to "
           "conceive, and what have you already tried so far?")


def test_a_question_the_opener_already_asked_is_flagged():
    """The phase-1 opener asks about duration and what she has tried. A lead who
    answers it partially sends us straight back to the same question, and the
    writer must reword it or the repeat check rejects the reply."""
    from app.services.brain.turn import already_asked

    history = [{"role": "assistant", "content": _OPENER}]
    assert already_asked(
        "how long she has been trying, and what she has already tried", history) is True


def test_an_unasked_question_is_not_flagged():
    from app.services.brain.turn import already_asked

    history = [{"role": "assistant", "content": _OPENER}]
    assert already_asked("her age", history) is False
    assert already_asked(
        "how much of a priority getting pregnant is for her right now", history) is False


def test_already_asked_ignores_what_the_lead_said():
    # Only Sonia's turns count; the lead using the same words is not us asking.
    from app.services.brain.turn import already_asked

    history = [{"role": "user", "content": "how long have you been trying to help people?"}]
    assert already_asked(
        "how long she has been trying, and what she has already tried", history) is False


def test_already_asked_handles_no_question():
    from app.services.brain.turn import already_asked
    assert already_asked(None, []) is False
    assert already_asked("some topic with no marker", [{"role": "assistant", "content": "x"}]) is False
