"""Reading a bare answer against the question the brain actually asked.

Every case here comes from the live AMH transcript of 2026-08-05, where the lead
answered "yes" four times and was asked the same question four times because the
answer settled nothing. No LLM: this is the layer that has to work when the
classifier returns nothing at all.
"""
import pytest

from app.services.brain import answers
from app.services.brain.constants import empty_lead_state
from app.services.brain.turn import _loop_guard, _next_question


# --- Yes / no ----------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "yes", "Yes!", "yeah", "yep", "sure", "absolutely", "definitely", "of course",
    "si", "sí", "claro", "100%", "yes please", "yes 🙏",
    "yes, that is exactly what I have been looking for",
])
def test_an_unmistakable_yes(text):
    assert answers.polarity(text) is True


@pytest.mark.parametrize("text", [
    "no", "nope", "not really", "no thanks", "not right now", "I can't",
    "no puedo", "ahora no",
])
def test_an_unmistakable_no(text):
    assert answers.polarity(text) is False


@pytest.mark.parametrize("text", [
    "",
    "hmm",
    "what does it include?",              # a question, not an answer
    "yes but I'd need to think about it",  # qualified: not ours to resolve
    "no idea what you mean",               # opens with "no", means nothing of the sort
    "I've been trying for 2 years",
])
def test_anything_less_than_unmistakable_resolves_nothing(text):
    assert answers.polarity(text) is None


# --- Resolving against the pending question ----------------------------------

def test_yes_to_the_paid_programme_question_settles_the_money():
    """The exact failure: four "yes"es to "would you be open to my paid
    programme?" left financial_ready null, so it was asked a fifth time."""
    assert answers.resolve("financial", ["yes"]) == {"financial_ready": True}


def test_no_to_the_paid_programme_question_settles_it_too():
    assert answers.resolve("financial", ["no, I can't"]) == {"financial_ready": False}


def test_yes_to_the_support_question_settles_the_role():
    assert answers.resolve("role", ["yes"]) == {"open_to_holistic": True}


def test_yes_to_the_partner_question_settles_whether_he_joins():
    assert answers.resolve("partner_join", ["yeah he can"]) == {"partner_can_join": True}


def test_a_question_with_no_binary_answer_resolves_nothing():
    """"Are you doing this with a partner or on your own" is not a yes/no."""
    assert answers.resolve("partner", ["yes"]) == {}


def test_nothing_pending_resolves_nothing():
    assert answers.resolve(None, ["yes"]) == {}


# --- The priority question ---------------------------------------------------

def test_a_number_is_the_priority_score():
    assert answers.resolve("priority", ["9"]) == {"priority_score": 9}
    assert answers.resolve("priority", ["about a 10 honestly"]) == {"priority_score": 10}


def test_very_high_is_readiness_not_an_invented_ten():
    """The classifier returned priority_score=10 quoting "very high". She never
    said a number, so the fact is readiness, not a score."""
    assert answers.resolve("priority", ["very high"]) == {"strong_readiness": True}
    assert answers.resolve("priority", ["it's the most important thing to me"]) == {
        "strong_readiness": True}


# --- Questions and their keys ------------------------------------------------

def test_every_question_key_has_a_topic_for_the_writer():
    for key in ("trying_duration", "age", "treatment_path", "done_testing",
                "diagnosis", "priority", "role", "financial", "partner",
                "partner_join"):
        assert answers.QUESTIONS.get(key), key


def test_every_yes_no_question_is_a_real_question_key():
    for key in answers.YES_NO_SLOT:
        assert key in answers.QUESTIONS


def test_every_slot_a_yes_no_answer_writes_exists():
    slots = empty_lead_state()["slots"]
    for slot in answers.YES_NO_SLOT.values():
        assert slot in slots


# --- The waterfall, by key ---------------------------------------------------

def _asked_everything_but_money():
    state = empty_lead_state()
    state["slots"].update({
        "trying_duration": "2 years", "age": 34, "what_tried": "low AMH result",
        "strong_readiness": True, "open_to_holistic": True,
    })
    state["flags"].update({"situation_shared": True, "explained_role": True})
    return state


def test_the_money_question_is_next_when_only_the_money_is_unknown():
    assert _next_question(_asked_everything_but_money()) == "financial"


def test_a_yes_moves_the_conversation_on():
    state = _asked_everything_but_money()
    state["slots"].update(answers.resolve("financial", ["yes"]))
    assert _next_question(state) == "partner"


def test_a_no_to_money_is_not_asked_again():
    """She said no. Asking a second time is nagging - and the booking gate keeps
    the link in either way."""
    state = _asked_everything_but_money()
    state["slots"].update(answers.resolve("financial", ["no thanks"]))
    assert _next_question(state) != "financial"


def test_deciding_which_question_to_ask_marks_nothing_as_done():
    """`explained_role` used to be set here - claiming the role had been
    explained at the moment we decided to ask about it, before the reply existed
    and even when the turn was later suppressed."""
    state = _asked_everything_but_money()
    state["slots"]["open_to_holistic"] = None
    assert _next_question(state) == "role"
    assert state["flags"]["explained_role"] is True  # from the fixture, not from us
    state["flags"]["explained_role"] = False
    _next_question(state)
    assert state["flags"]["explained_role"] is False


# --- The loop guard ----------------------------------------------------------

def test_the_same_question_three_times_running_goes_to_a_human():
    state = empty_lead_state()
    assert _loop_guard(state, "financial") is False   # first ask
    assert _loop_guard(state, "financial") is False   # second ask, she dodged
    assert _loop_guard(state, "financial") is True    # a third is a person's job


def test_a_different_question_resets_the_guard():
    state = empty_lead_state()
    _loop_guard(state, "financial")
    _loop_guard(state, "financial")
    assert _loop_guard(state, "partner") is False
    assert state["counters"]["repeat_count"] == 0


def test_a_turn_that_asks_nothing_clears_the_guard():
    state = empty_lead_state()
    _loop_guard(state, "role")
    _loop_guard(state, "role")
    assert _loop_guard(state, None) is False
    assert state["flags"]["last_prompt"] is None
    assert state["counters"]["repeat_count"] == 0
