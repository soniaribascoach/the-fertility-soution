"""Pure tests for the fit assessment (no LLM, no DB).

`likely_not_a_fit` decides whether Sonia should honestly tell someone they may
not need this yet. It runs on facts the lead stated, never on model judgement,
so every case here is a plain dictionary.
"""
import pytest

from app.services.brain.constants import empty_lead_state
from app.services.brain.gates import likely_not_a_fit, months_trying


def state(**slots):
    st = empty_lead_state()
    st["slots"].update(slots)
    return st


# --- duration parsing --------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("3 months", 3),
    ("about 3 months", 3),
    ("4 mo", 4),
    ("2 years", 24),
    ("a year", 12),
    ("a couple of years", 24),
    ("a few months", 3),
    ("6 weeks", 1.5),
    ("1.5 years", 18),
])
def test_months_trying_parses_her_words(text, expected):
    assert months_trying(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", [None, "", "a while", "on and off", "forever"])
def test_unparseable_duration_is_unknown_not_zero(text):
    # "a while" must never be read as a short time - that would declare a
    # long-term struggler a poor fit.
    assert months_trying(text) is None


# --- the assessment ----------------------------------------------------------

def test_young_and_early_with_nothing_else_is_not_a_fit():
    # Sonia's own example: 29, trying naturally 3 months, nothing tried.
    assert likely_not_a_fit(state(age=29, trying_duration="3 months")) is True


def test_older_woman_trying_briefly_is_still_a_fit():
    assert likely_not_a_fit(state(age=41, trying_duration="3 months")) is False


def test_long_duration_is_a_fit():
    assert likely_not_a_fit(state(age=29, trying_duration="3 years")) is False


@pytest.mark.parametrize("extra", [
    {"diagnosis": "confirmed"},
    {"diagnosis_detail": "PCOS"},
    {"what_tried": "clomid"},
    {"done_testing": True},
    {"treatment_path": "ivf"},
    {"tubes_blocked": "one"},
])
def test_any_real_difficulty_makes_her_a_fit(extra):
    # A 29-year-old three months in with PCOS or a blocked tube is exactly who
    # Sonia should help; the early-days rule must not swallow her.
    assert likely_not_a_fit(state(age=29, trying_duration="3 months", **extra)) is False


@pytest.mark.parametrize("slots", [
    {"trying_duration": "3 months"},          # age unknown
    {"age": 29},                              # duration unknown
    {"age": 29, "trying_duration": "a while"},  # duration unparseable
    {},
])
def test_unknown_facts_never_declare_a_poor_fit(slots):
    # Every condition needs positive knowledge. Absence of information is not
    # evidence that she does not need help.
    assert likely_not_a_fit(state(**slots)) is False


def test_boundary_is_inclusive_of_help():
    # 35 and 6 months are the edges; at the edge we keep helping.
    assert likely_not_a_fit(state(age=35, trying_duration="3 months")) is False
    assert likely_not_a_fit(state(age=29, trying_duration="6 months")) is False
