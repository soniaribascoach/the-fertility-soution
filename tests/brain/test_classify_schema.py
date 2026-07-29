"""Pure schema-consistency tests for the classifier (no LLM, no DB).

Mirrors test_extractor_schema.py: these are drift guards, not behaviour tests.
The classifier's schema is the contract between the LLM and the router, so a
silent mismatch here is the kind of bug that only shows up in production.
"""
from typing import get_args

import pytest

from app.services.brain.classify import (
    Classification,
    Evidence,
    SlotDeltas,
    _INTENT_LITERAL,
    verify_evidence,
)
from app.services.brain.constants import (
    NEVER_QUALIFY,
    SLOT_KEYS,
    LeadIntent,
    ResponseMode,
    Stage,
)


def test_intent_literal_matches_enum():
    # The classifier's Literal and the LeadIntent enum must stay in lockstep,
    # or the router will receive a label it has no branch for.
    assert set(get_args(_INTENT_LITERAL)) == {i.value for i in LeadIntent}


def test_secondary_intent_uses_the_same_vocabulary():
    ann = Classification.model_fields["secondary_intent"].annotation
    # Optional[Literal[...]] -> the Literal is the first non-None arg
    literal = next(a for a in get_args(ann) if a is not type(None))  # noqa: E721
    assert set(get_args(literal)) == {i.value for i in LeadIntent}


def test_slot_deltas_fields_are_known_slots():
    for field in SlotDeltas.model_fields:
        assert field in SLOT_KEYS, f"{field} is not in SLOT_KEYS"


def test_language_literal_values_and_position():
    assert set(get_args(Classification.model_fields["language"].annotation)) == {
        "en", "es", "other", "unclear",
    }
    # Structured outputs generate fields in schema order and the raw text must be
    # judged before it is digested into the English fields. Placing `language`
    # later made French read as Spanish. Guard the position, not just the values.
    assert list(Classification.model_fields)[0] == "language"


def test_never_qualify_members_are_real_intents():
    for intent in NEVER_QUALIFY:
        assert isinstance(intent, LeadIntent)


def test_response_modes_are_distinct_from_stages():
    # Both are short uppercase-ish enums; a copy-paste between them would be easy
    # to miss and would silently mis-route.
    assert {m.value for m in ResponseMode} & {s.value for s in Stage} == set()


# --- verify_evidence ---------------------------------------------------------

def _classification(**overrides):
    base = dict(
        language="en",
        intent="answers_question",
        intent_certainty="certain",
        secondary_intent=None,
        question_asked=None,
        slot_deltas=SlotDeltas(**{k: None for k in SlotDeltas.model_fields}),
        evidence=[],
        situation_richness="none",
        situation_type="none",
        oos_signal="none",
        off_script=False,
        takeover=False,
        takeover_reason=None,
    )
    base.update(overrides)
    return Classification(**base)


def test_quoted_fact_is_kept():
    c = _classification(
        slot_deltas=SlotDeltas(**{**{k: None for k in SlotDeltas.model_fields}, "age": 38}),
        evidence=[Evidence(slot="age", quote="I'm 38", certainty="certain")],
    )
    verified, rejected = verify_evidence(c, ["I'm 38 and we've been trying a while"])
    assert verified == {"age": 38}
    assert rejected == []


def test_fabricated_quote_loses_the_fact():
    # The model claims she gave her age and invents the words. Without the
    # substring check this is exactly how a hallucinated fact enters lead state.
    c = _classification(
        slot_deltas=SlotDeltas(**{**{k: None for k in SlotDeltas.model_fields}, "age": 38}),
        evidence=[Evidence(slot="age", quote="I am 38 years old", certainty="certain")],
    )
    verified, rejected = verify_evidence(c, ["hi, can you help me?"])
    assert verified == {}
    assert rejected == ["age"]


def test_unevidenced_fact_is_dropped():
    # A delta with no evidence entry at all: if she really said it, there would
    # be something to quote.
    c = _classification(
        slot_deltas=SlotDeltas(
            **{**{k: None for k in SlotDeltas.model_fields}, "partner_is_decision_maker": True}
        ),
        evidence=[],
    )
    verified, rejected = verify_evidence(c, ["he can't make it to the call"])
    assert verified == {}
    assert rejected == ["partner_is_decision_maker"]


def test_quote_matching_folds_case_and_whitespace():
    c = _classification(
        slot_deltas=SlotDeltas(
            **{**{k: None for k in SlotDeltas.model_fields}, "trying_duration": "2 years"}
        ),
        evidence=[Evidence(slot="trying_duration", quote="Trying   For  2 Years",
                           certainty="certain")],
    )
    verified, _ = verify_evidence(c, ["we have been trying for 2 years now"])
    assert verified == {"trying_duration": "2 years"}


def test_unevidenced_and_fabricated_are_reported_separately():
    """They mean different things and must not be conflated.

    An inference with no quote offered is routine (the model likes to conclude
    `diagnosis="none"` from a message that never mentions one) and says nothing
    about the turn. A quote that IS offered and does not appear in her message
    means the model invented her words, which is alarming.
    """
    c = _classification(
        slot_deltas=SlotDeltas(**{
            **{k: None for k in SlotDeltas.model_fields},
            "diagnosis": "none",   # inferred, no quote offered
            "age": 38,             # quoted, but the quote is invented
        }),
        evidence=[Evidence(slot="age", quote="I am 38 years old", certainty="certain")],
    )
    result = verify_evidence(c, ["hi, can you help me?"])
    assert result.verified == {}
    assert result.unevidenced == ["diagnosis"]
    assert result.fabricated == ["age"]


def test_evidence_result_still_unpacks_as_a_pair():
    c = _classification(
        slot_deltas=SlotDeltas(**{**{k: None for k in SlotDeltas.model_fields}, "age": 38}),
        evidence=[Evidence(slot="age", quote="I'm 38", certainty="certain")],
    )
    verified, rejected = verify_evidence(c, ["I'm 38"])
    assert verified == {"age": 38}
    assert rejected == []


def test_unsure_evidence_is_discarded_even_when_quotable():
    # The quote is real, but the model would not stand behind the reading. A
    # doubtful fact must never silently gate a booking.
    c = _classification(
        slot_deltas=SlotDeltas(
            **{**{k: None for k in SlotDeltas.model_fields}, "financial_ready": True}
        ),
        evidence=[Evidence(slot="financial_ready", quote="count me in", certainty="unsure")],
    )
    verified, rejected = verify_evidence(c, ["yes count me in!"])
    assert verified == {}
    assert rejected == ["financial_ready"]


def test_certainty_is_discrete_not_a_float():
    # gpt-4o-mini returns ~0.9 for everything, including a contentless "ok", so a
    # float carries no signal. Guard the schema against a regression to one.
    ann = Classification.model_fields["intent_certainty"].annotation
    assert set(get_args(ann)) == {"certain", "probable", "unsure"}
    assert set(get_args(Evidence.model_fields["certainty"].annotation)) == {
        "certain", "probable", "unsure",
    }


@pytest.mark.parametrize("quote", ["", "   "])
def test_empty_quote_is_not_a_free_pass(quote):
    # An empty quote is a substring of everything; it must not verify a fact.
    c = _classification(
        slot_deltas=SlotDeltas(**{**{k: None for k in SlotDeltas.model_fields}, "age": 41}),
        evidence=[Evidence(slot="age", quote=quote, certainty="certain")],
    )
    verified, rejected = verify_evidence(c, ["hello"])
    assert verified == {}
    assert rejected == ["age"]
