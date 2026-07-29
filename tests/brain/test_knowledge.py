"""Pure knowledge-retrieval tests (no LLM, no DB).

Retrieval decides what substance the writer is allowed to use, which is how
"answer her question" is made safe and how the four objection types stop
collapsing into one reply.
"""
import pytest

from app.services.brain.constants import LeadIntent, ResponseMode
from app.services.brain.knowledge import (
    Kind,
    KnowledgeEntry,
    parse_pattern_responses,
    select,
)
from app.services.brain.knowledge_seed import SEED


def entry(kind, topic, triggers, content="x", language="en", active=True):
    return KnowledgeEntry(kind=kind, topic=topic, content=content,
                          triggers=triggers, language=language, active=active)


# --- parsing the client's existing reframes ----------------------------------

_RAW = (
    "Low AMH: Low AMH does not mean no baby. What matters is quality, not quantity.\n"
    "PCOS: With PCOS, the goal is helping the body feel safe enough to regulate.\n"
    "\n"
    "not a valid line\n"
    "Failed IVF: A failed cycle doesn't mean your body failed.\n"
)


def test_pattern_responses_parse_into_entries():
    entries = parse_pattern_responses(_RAW)
    assert [e.topic for e in entries] == ["low_amh", "pcos", "failed_ivf"]
    assert all(e.kind == Kind.REFRAME for e in entries)
    assert entries[0].content.startswith("Low AMH does not mean no baby")


def test_parsed_entries_are_retrievable_by_her_words():
    entries = parse_pattern_responses(_RAW)
    got = select(entries, mode=ResponseMode.ANSWER,
                 intent=LeadIntent.GENERAL_FERTILITY_QUESTION,
                 text="my doctor said my AMH is 0.6 and pushed me to IVF")
    assert "low_amh" in [e.topic for e in got]


def test_unknown_topic_still_gets_usable_triggers():
    # An entry Sonia types in tomorrow must be retrievable without code changes.
    entries = parse_pattern_responses("Thyroid concerns: your thyroid matters here.")
    got = select(entries, mode=ResponseMode.ANSWER, intent=LeadIntent.GENERAL_FERTILITY_QUESTION,
                 text="my thyroid results were borderline")
    assert [e.topic for e in got] == ["thyroid_concerns"]


def test_malformed_lines_are_skipped_not_fatal():
    assert parse_pattern_responses("") == []
    assert parse_pattern_responses("no colon here") == []
    assert parse_pattern_responses("Topic only:") == []


# --- retrieval ---------------------------------------------------------------

def test_nothing_matched_returns_nothing():
    entries = [entry(Kind.REFRAME, "pcos", [r"\bpcos\b"])]
    assert select(entries, mode=ResponseMode.ANSWER, intent=LeadIntent.ANSWERS_QUESTION,
                  text="hello there") == []


def test_more_specific_match_ranks_higher():
    generic = entry(Kind.REFRAME, "generic", [r"fertility"])
    specific = entry(Kind.REFRAME, "low_amh", [r"\bamh\b", r"egg.{0,5}reserve", r"fertility"])
    got = select([generic, specific], mode=ResponseMode.ANSWER,
                 intent=LeadIntent.GENERAL_FERTILITY_QUESTION,
                 text="my AMH is low, my egg reserve is bad, fertility is hard")
    assert got[0].topic == "low_amh"


@pytest.mark.parametrize("intent,topic", [
    (LeadIntent.OBJECTION_PRICE, "price"),
    (LeadIntent.OBJECTION_PARTNER, "partner"),
    (LeadIntent.OBJECTION_TRUST, "trust"),
    (LeadIntent.OBJECTION_FEAR_AFTER_FAILURE, "fear_after_failure"),
    (LeadIntent.OBJECTION_PAYING_TWICE, "paying_twice"),
])
def test_each_objection_pulls_its_own_entry(intent, topic):
    """Complaint 6: these must not all receive the same generic reply."""
    got = select(SEED, mode=ResponseMode.ANSWER, intent=intent, text="")
    assert got, f"no knowledge retrieved for {intent}"
    assert got[0].kind == Kind.OBJECTION
    assert got[0].topic == topic


def test_objection_entry_survives_even_with_many_other_matches():
    noisy = [entry(Kind.REFRAME, f"r{i}", [r"the"]) for i in range(10)]
    got = select(SEED + noisy, mode=ResponseMode.ANSWER,
                 intent=LeadIntent.OBJECTION_PRICE,
                 text="the the the the how much does the programme cost")
    assert any(e.kind == Kind.OBJECTION and e.topic == "price" for e in got)


def test_mode_filters_what_is_offered():
    # A CELEBRATE turn gets no positioning: nobody pitches at a pregnancy
    # announcement.
    assert select(SEED, mode=ResponseMode.CELEBRATE, intent=LeadIntent.PREGNANCY_OR_SUCCESS,
                  text="I'm pregnant!") == []
    assert select(SEED, mode=ResponseMode.BOOK, intent=LeadIntent.WARM_HIGH_INTENT,
                  text="send me the link") == []


def test_educate_always_gets_positioning():
    """Complaint 5. An EDUCATE turn must never fall back on generic wellness
    language just because nothing in her message matched a trigger."""
    got = select(SEED, mode=ResponseMode.EDUCATE, intent=LeadIntent.OBJECTION_TRUST,
                 text="hmm")
    assert any(e.kind == Kind.POSITIONING for e in got)


def test_honest_decline_gets_not_a_fit_copy():
    got = select(SEED, mode=ResponseMode.HONEST_DECLINE, intent=LeadIntent.ANSWERS_QUESTION,
                 text="should I join?")
    assert [e.kind for e in got] == [Kind.NOT_A_FIT]


def test_inactive_and_wrong_language_entries_are_excluded():
    off = entry(Kind.REFRAME, "pcos", [r"\bpcos\b"], active=False)
    es = entry(Kind.REFRAME, "pcos_es", [r"\bpcos\b"], language="es")
    got = select([off, es], mode=ResponseMode.ANSWER, intent=LeadIntent.ANSWERS_QUESTION,
                 text="I have pcos")
    assert got == []


def test_language_selects_the_right_entry():
    en = entry(Kind.REFRAME, "pcos", [r"\bpcos\b"], content="EN")
    es = entry(Kind.REFRAME, "pcos", [r"\bpcos\b"], content="ES", language="es")
    got = select([en, es], mode=ResponseMode.ANSWER, intent=LeadIntent.ANSWERS_QUESTION,
                 text="tengo pcos", language="es")
    assert [e.content for e in got] == ["ES"]


def test_a_broken_admin_regex_does_not_break_the_turn():
    """Someone will eventually type an unbalanced bracket into the admin panel."""
    bad = entry(Kind.REFRAME, "oops", ["[unclosed", "pcos"])
    got = select([bad], mode=ResponseMode.ANSWER, intent=LeadIntent.ANSWERS_QUESTION,
                 text="I have pcos")
    assert [e.topic for e in got] == ["oops"]


def test_limit_is_respected():
    entries = [entry(Kind.REFRAME, f"r{i}", [r"fertility"]) for i in range(10)]
    got = select(entries, mode=ResponseMode.ANSWER, intent=LeadIntent.ANSWERS_QUESTION,
                 text="fertility", limit=3)
    assert len(got) == 3


# --- the seed itself ----------------------------------------------------------

def test_seed_entries_are_well_formed():
    for e in SEED:
        assert e.kind in Kind.ALL, f"{e.topic} has unknown kind {e.kind}"
        assert e.content.strip(), f"{e.topic} has no content"
        assert e.triggers, f"{e.topic} has no triggers and can never be retrieved"
        assert e.source, f"{e.topic} does not say where it came from"


def test_seed_covers_every_objection_type():
    topics = {e.topic for e in SEED if e.kind == Kind.OBJECTION}
    assert topics == {"price", "partner", "trust", "fear_after_failure", "paying_twice"}


def test_seed_positioning_is_not_generic_wellness_copy():
    """Complaint 5, as a regression test.

    The rejected phrasing listed 'nutrition, hormones, stress and lifestyle' as
    the whole offer, which describes any wellness coach. Positioning entries must
    say something more specific than that laundry list.
    """
    positioning = " ".join(e.content.casefold() for e in SEED if e.kind == Kind.POSITIONING)
    assert "alongside" in positioning or "rather than replacing" in positioning
    generic_only = {"nutrition", "hormones", "stress", "lifestyle"}
    words = set(positioning.replace(",", " ").split())
    assert not words.issubset(generic_only)
