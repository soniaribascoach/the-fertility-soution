"""Pure uncertainty-scoring tests (no LLM, no DB).

Sonia asked that anything the bot is not sure about goes to a person. That used
to be six unrelated code paths; here it is one number against one threshold, so
it can actually be tuned and tested.
"""
import pytest

from app.services.brain.uncertainty import (
    DEFAULT_THRESHOLD,
    score_turn,
    should_check,
    threshold_from,
)


def score(**overrides):
    base = dict(
        intent_certainty="certain", off_script=False, fabricated_slots=[],
        contradictions=[], writer_unsure=False, code_violations=[],
        checker_violations=[], regenerated=False, still_failing=False, repeat_count=0,
    )
    base.update(overrides)
    return score_turn(**base)


def test_a_clean_turn_scores_zero():
    u = score()
    assert u.score == 0
    assert not u.over(DEFAULT_THRESHOLD)


@pytest.mark.parametrize("kwargs", [
    {"intent_certainty": "unsure"},
    {"off_script": True},
    {"contradictions": ["age"]},
    {"checker_violations": ["faithful:she said her AMH was fine"]},
    {"checker_violations": ["premature:let's get you booked"]},
    {"code_violations": ["invented_number:0.6"]},
    # A quote that is not in her message means the model invented her words, so
    # nothing it extracted this turn can be trusted.
    {"fabricated_slots": ["age"]},
    # Two attempts and the rules are still broken. Without this a banned phrase
    # or a second question survives both passes and is sent anyway.
    {"regenerated": True, "still_failing": True, "code_violations": ["banned_phrase:i hear you"]},
])
def test_any_single_serious_signal_reaches_a_human(kwargs):
    """One strong signal is enough on its own - the point of shipping strict."""
    assert score(**kwargs).over(DEFAULT_THRESHOLD)


@pytest.mark.parametrize("kwargs", [
    {"regenerated": True},
    {"code_violations": ["em_dash"]},
    {"intent_certainty": "probable"},
])
def test_a_single_weak_signal_does_not(kwargs):
    """Otherwise every imperfect turn would be handed over and the AI would
    never speak."""
    assert not score(**kwargs).over(DEFAULT_THRESHOLD)


def test_weak_signals_accumulate():
    u = score(intent_certainty="probable", regenerated=True,
              code_violations=["em_dash", "too_long"])
    assert u.over(DEFAULT_THRESHOLD)


def test_signals_are_named_for_the_trace():
    u = score(off_script=True, writer_unsure=True)
    assert "off_script" in u.signals and "writer_unsure" in u.signals


def test_repeated_slots_count_more_than_one():
    single = score(fabricated_slots=["a"]).score
    triple = score(fabricated_slots=["a", "b", "c"]).score
    assert triple > single


def test_a_dodged_question_is_weaker_than_an_invented_fact():
    """Not answering is bad; making something up is worse."""
    assert (score(checker_violations=["answered:it deflected"]).score
            < score(checker_violations=["faithful:invented"]).score)


def test_unavailable_checker_does_not_silently_pass():
    assert score(checker_violations=["checker_unavailable:faithful"]).score > 0


# --- the threshold knob -------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ({"uncertainty_threshold": "5"}, 5),
    ({"uncertainty_threshold": 2}, 2),
    ({}, DEFAULT_THRESHOLD),
    ({"uncertainty_threshold": ""}, DEFAULT_THRESHOLD),
    ({"uncertainty_threshold": "nonsense"}, DEFAULT_THRESHOLD),
    ({"uncertainty_threshold": "0"}, DEFAULT_THRESHOLD),
    (None, DEFAULT_THRESHOLD),
])
def test_threshold_is_config_driven_and_never_breaks_on_bad_input(raw, expected):
    assert threshold_from(raw) == expected


def test_raising_the_threshold_lets_a_turn_through():
    u = score(intent_certainty="probable", regenerated=True,
              code_violations=["em_dash", "too_long"])
    assert u.over(3)
    assert not u.over(10)


# --- when the veto panel is worth its call ------------------------------------

def base_check(**overrides):
    args = dict(intent_certainty="certain", off_script=False, writer_unsure=False,
                code_violations=[], gate_just_opened=False, question_asked=None)
    args.update(overrides)
    return should_check(**args)


def test_a_routine_turn_skips_the_panel():
    assert base_check() is False


@pytest.mark.parametrize("kwargs", [
    {"gate_just_opened": True},
    {"question_asked": "can anything help before IVF?"},
    {"writer_unsure": True},
    {"off_script": True},
    {"code_violations": ["em_dash"]},
    {"intent_certainty": "probable"},
])
def test_the_panel_runs_when_it_matters(kwargs):
    assert base_check(**kwargs) is True
