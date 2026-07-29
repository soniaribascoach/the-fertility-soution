"""Live classifier tests - the contract with the client.

Every case below is a scenario Sonia reported broken in her 2026-07-29 review.
The classifier is the load-bearing call in the new brain: if a pregnancy
announcement is read as a new prospect, every downstream decision is wrong.
So these run against the real model, not a mock.

    pytest -m live tests/brain/test_classify.py
"""
import pytest

from app.services.brain.classify import classify, verify_evidence
from app.services.brain.constants import NEVER_QUALIFY, LeadIntent, empty_lead_state
from app.services.brain.gates import likely_not_a_fit, months_trying

pytestmark = pytest.mark.live


def _history(*user_msgs, sonia=None):
    """Build a transcript. `sonia` interleaves Sonia's turns before each reply."""
    history = []
    for i, msg in enumerate(user_msgs):
        if sonia and i < len(sonia) and sonia[i]:
            history.append({"role": "assistant", "content": sonia[i]})
        history.append({"role": "user", "content": msg})
    return history


async def _classify(openai_client, *user_msgs, sonia=None, slots=None):
    history = _history(*user_msgs, sonia=sonia)
    result, _ = await classify(openai_client, history, slots or {})
    return result


# --- Complaint 1 + 7: these must never enter the sales funnel ----------------

@pytest.mark.parametrize("message,expected", [
    # She is pregnant. Sonia: "it asked qualifying questions after someone
    # shared that she was pregnant."
    ("I just found out I'm pregnant!! I can't believe it, thank you so much",
     LeadIntent.PREGNANCY_OR_SUCCESS),
    ("We got our BFP this morning after 3 years of trying 🥹",
     LeadIntent.PREGNANCY_OR_SUCCESS),
    # Pure thanks. Sonia: "it asked qualifying questions after someone thanked
    # me for my content."
    ("Just wanted to say thank you for your posts, they've helped me so much",
     LeadIntent.GRATITUDE),
    ("your content is amazing, thank you for everything you share",
     LeadIntent.GRATITUDE),
    # She has stopped. Sonia: "after someone said she had decided to stop
    # trying for a baby."
    ("We've decided to stop trying. I'm at peace with it but it's been a lot.",
     LeadIntent.GRIEF_OR_STOPPED_TRYING),
    ("I'm done. After 6 years I can't do this anymore.",
     LeadIntent.GRIEF_OR_STOPPED_TRYING),
])
async def test_non_sales_intents(openai_client, message, expected):
    result = await _classify(openai_client, message)
    assert result.intent == expected.value, f"got {result.intent} for {message!r}"
    assert LeadIntent(result.intent) in NEVER_QUALIFY


# --- Complaint 3: she asked something. Answer it. ---------------------------

async def test_pre_ivf_question_is_a_question_not_a_lead(openai_client):
    """Sonia: 'when someone asked whether anything could realistically make a
    difference in the 6 weeks before IVF, the AI avoided answering and moved
    straight back into qualification.'"""
    result = await _classify(
        openai_client,
        "I start IVF in 6 weeks. Is there realistically anything that can make a "
        "difference in that time?",
    )
    assert result.intent == LeadIntent.GENERAL_FERTILITY_QUESTION.value
    assert result.question_asked, "her question must be carried forward verbatim"
    assert "6 weeks" in result.question_asked or "difference" in result.question_asked


async def test_question_asked_is_null_when_she_asks_nothing(openai_client):
    result = await _classify(openai_client, "we've been trying for about two years now")
    assert result.question_asked is None


async def test_free_advice_request_is_distinguished(openai_client):
    result = await _classify(
        openai_client, "what supplements should I be taking for low AMH?"
    )
    assert result.intent == LeadIntent.ASKS_FREE_ADVICE.value


# --- Complaint 6: objections are four different conversations ---------------

@pytest.mark.parametrize("message,expected", [
    ("how much does your program cost?", LeadIntent.OBJECTION_PRICE),
    ("honestly that's way out of our budget right now",
     LeadIntent.OBJECTION_PRICE),
    ("my husband thinks coaching is a waste of money, he doesn't believe in it",
     LeadIntent.OBJECTION_PARTNER),
    ("how do I know this actually works? feels like there are a lot of people "
     "online claiming they can help", LeadIntent.OBJECTION_TRUST),
    ("after 4 failed transfers I'm terrified of getting my hopes up again",
     LeadIntent.OBJECTION_FEAR_AFTER_FAILURE),
    ("I'm already paying my clinic a fortune, why would I pay for this too",
     LeadIntent.OBJECTION_PAYING_TWICE),
])
async def test_objection_subtypes_are_distinct(openai_client, message, expected):
    result = await _classify(openai_client, message)
    assert result.intent == expected.value, f"got {result.intent} for {message!r}"


# --- Complaint 2: read what she already told you ----------------------------

async def test_rich_situation_is_recognised(openai_client):
    """Sonia: 'someone explained that she had completed 4 IVF cycles, changed her
    diet, taken supplements and worked with several practitioners. The AI then
    asked what else she had already tried.'"""
    result = await _classify(
        openai_client,
        "I've done 4 IVF cycles, completely changed my diet, taken every supplement "
        "you can think of and worked with 3 different practitioners. Nothing has worked.",
    )
    assert result.situation_richness == "rich"
    assert result.slot_deltas.what_tried, "what she tried must be captured"


async def test_dated_treatment_plan_reads_as_readiness(openai_client):
    """Sonia: 'Another prospect said she was preparing for IVF in September, but
    the AI continued asking how much of a priority pregnancy was.'"""
    result = await _classify(
        openai_client, "I'm preparing for IVF in September"
    )
    assert result.slot_deltas.strong_readiness is True, (
        "a concrete dated plan already answers the priority question"
    )


# --- Complaint 7: recognise not-a-fit and ready-to-book ---------------------

async def test_probably_not_a_fit_facts_are_captured(openai_client):
    """Sonia: 'when someone asked whether she should join the program after
    trying naturally for only 3 months at age 29, the AI described my services
    instead of honestly assessing whether she may even need this level of
    support.'

    Whether she is a fit is decided in code by `gates.likely_not_a_fit`, not by
    the model - "should she join" is an assessment of facts, and asking the LLM
    to make it was unreliable. The classifier's only job here is to capture the
    facts that assessment needs.
    """
    message = "I'm 29 and we've been trying naturally for 3 months. Should I join your program?"
    result = await _classify(openai_client, message)
    verified, _ = verify_evidence(result, [message])
    assert verified.get("age") == 29
    assert verified.get("trying_duration")
    assert months_trying(verified["trying_duration"]) == pytest.approx(3)

    state = empty_lead_state()
    state["slots"].update(verified)
    assert likely_not_a_fit(state) is True


async def test_high_intent_is_recognised(openai_client):
    result = await _classify(openai_client, "this sounds exactly like what I need, how do I start?")
    assert result.intent == LeadIntent.WARM_HIGH_INTENT.value


# --- Evidence verification --------------------------------------------------

async def test_extracted_facts_are_quotable(openai_client):
    """Facts she actually stated survive verification.

    Facts the model INFERS (it likes to set `diagnosis` from "2 failed IUIs")
    have nothing to quote and are dropped. That is the mechanism working, so
    this asserts on what survives rather than demanding an empty reject list.
    """
    message = "I'm 38, we've been trying for 2 years and I've done 2 failed IUIs"
    result = await _classify(openai_client, message)
    verified, rejected = verify_evidence(result, [message])
    assert verified.get("age") == 38
    assert verified.get("trying_duration")
    for stated in ("age", "trying_duration"):
        assert stated not in rejected, f"{stated} was stated outright but got rejected"


async def test_partner_refusal_does_not_invent_a_decision_maker(openai_client):
    """The old extractor over-inferred `partner_is_decision_maker` in both
    directions from 'he can't make it', which needed a hand-written patch in
    merge(). With evidence required, there is nothing to quote, so nothing is set."""
    message = "my husband can't make it to the call, he works nights"
    result = await _classify(
        openai_client, message,
        sonia=["Would your partner be able to join the call?"],
    )
    verified, _ = verify_evidence(result, [message])
    assert "partner_is_decision_maker" not in verified


# --- Escalation and uncertainty ---------------------------------------------

async def test_mild_venting_is_not_distress(openai_client):
    result = await _classify(
        openai_client, "it's been really hard and discouraging honestly",
        sonia=["On a scale of 1 to 10, how much of a priority is getting pregnant?"],
    )
    assert result.intent != LeadIntent.DISTRESS.value
    assert result.takeover is False
    assert result.slot_deltas.priority_score is None, (
        "an emotional non-answer is not a low score"
    )


@pytest.mark.parametrize("message,expected", [
    ("is this a bot? am I talking to a real person", LeadIntent.IS_THIS_AI),
    ("I'm already a client, I have a question about my next session",
     LeadIntent.EXISTING_CLIENT),
    ("Hi, I run a fertility podcast and would love to have you on",
     LeadIntent.COLLABORATION_OR_TECHNICAL),
])
async def test_escalation_and_non_prospect_intents(openai_client, message, expected):
    result = await _classify(openai_client, message)
    assert result.intent == expected.value, f"got {result.intent} for {message!r}"


async def test_contentless_message_is_reported_as_unsure(openai_client):
    """A bare "ok" with no preceding question carries no purpose of its own.

    We do not assert a specific intent - the point is that the classifier admits
    it cannot tell, which is what routes the turn to a human instead of guessing.
    """
    result = await _classify(openai_client, "ok")
    assert result.intent_certainty == "unsure", (
        f"'ok' classified as {result.intent} with certainty {result.intent_certainty}"
    )


@pytest.mark.parametrize("sonia_turn,reply,slot,value", [
    ("Is that the kind of support you're looking for?", "yes", "open_to_holistic", True),
    ("How old are you?", "38", "age", 38),
    ("Have you done any fertility testing yet?", "not yet", "done_testing", False),
])
async def test_short_answer_in_context_is_not_unsure(
    openai_client, sonia_turn, reply, slot, value
):
    """The mirror of the previous test: a bare answer following a question is
    unambiguous, and the fact it carries must land.

    Without this, the fix for `test_contentless_message_is_reported_as_unsure`
    would be "always say unsure", which routes every conversation to a human.

    Note we assert the CERTAINTY and the extracted fact, not the intent label.
    A "yes" to the fit question reads as warm_high_intent about as often as
    answers_question, and that distinction is not load-bearing: warm_high_intent
    only reaches BOOK when `booking_gate()` passes, so the gate decides either
    way. `open_to_holistic` landing is what actually moves the funnel.
    """
    result = await _classify(openai_client, reply, sonia=[sonia_turn])
    assert result.intent_certainty in ("certain", "probable")
    assert getattr(result.slot_deltas, slot) == value
