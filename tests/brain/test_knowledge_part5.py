"""Part 5 facts: the manual's single source of truth, as data.

The point of this module is that a fact stated in two places drifts. The running
code claimed "15 years" in writer.py and "over 700 families" in
prompt_builder.py at the same time, which is the failure these tests guard.
"""
import pytest

from app.services.brain.knowledge import Kind, KINDS_FOR_MODE, select
from app.services.brain.knowledge_part5 import PART5
from app.services.brain.knowledge_seed import SEED
from app.services.brain.constants import LeadIntent, ResponseMode


def test_part5_is_in_the_seed():
    topics = {e.topic for e in SEED if e.kind == Kind.FACT}
    assert {e.topic for e in PART5} <= topics


def test_no_duplicate_kind_topic_pairs():
    """Retrieval keys on kind+topic, and the migration upserts on it."""
    keys = [(e.kind, e.topic) for e in SEED]
    assert len(keys) == len(set(keys))


def test_the_one_price_matches_the_one_the_funnel_brain_quotes():
    """The price lives in two places by necessity: here for the routed brain and
    `scripts._PLACEHOLDER_DEFAULTS` for the funnel brain. Two different numbers
    reaching two different leads is the failure mode, so they must agree.

    Resolved 2026-08-04: the client confirmed $1,500 to $14,000 is current, which
    means the manual's $1,500-$10,000 (2B.2 section 6) is out of date.
    """
    import re

    from app.services.brain.scripts import placeholders

    pricing = next(e for e in PART5 if e.topic == "pricing_range")
    assert pricing.active is True

    # Trailing punctuation is not part of the figure: "$14,000," must equal
    # "$14,000".
    money = r"\$[\d,]*\d"
    figures = set(re.findall(money, pricing.content))
    config = set(re.findall(money, placeholders({})["price_range"]))
    assert figures == config, f"knowledge says {figures}, scripts say {config}"


def test_the_superseded_manual_figure_appears_nowhere():
    """A stale price is worse than no price."""
    for entry in SEED:
        assert "$10,000" not in entry.content, f"{entry.kind}/{entry.topic}"


def test_only_the_pricing_entry_states_a_price():
    """Any other entry naming a figure is a second source that will drift."""
    for entry in SEED:
        if entry.active and entry.topic != "pricing_range":
            assert "$" not in entry.content, (
                f"{entry.kind}/{entry.topic} states a price; pricing_range is "
                f"the only entry that may"
            )


def test_credentials_match_the_manual():
    proof = next(e for e in SEED if e.kind == Kind.PROOF and e.topic == "track_record")
    assert "735" in proof.content and "Sixteen" in proof.content
    assert "fifteen" not in proof.content.casefold()
    assert "seven hundred" not in proof.content.casefold()


@pytest.mark.parametrize("mode", [ResponseMode.CELEBRATE, ResponseMode.ACKNOWLEDGE,
                                  ResponseMode.QUALIFY])
def test_facts_are_not_retrievable_where_they_do_not_belong(mode):
    """A celebration or a moment of grief has no business quoting credentials."""
    assert Kind.FACT not in KINDS_FOR_MODE[mode]


def test_a_program_question_can_reach_the_facts():
    retrieved = select(SEED, mode=ResponseMode.ANSWER,
                       intent=LeadIntent.ASKS_ABOUT_PROGRAM,
                       text="are you a doctor? what do you do exactly?")
    assert any(e.kind == Kind.FACT for e in retrieved), \
        "a question about what she does retrieves no facts at all"


def test_every_part5_entry_is_attributed():
    """Every fact says where it came from, so a stale one can be traced. An
    entry may cite the manual, or cite the client overriding it - pricing does
    the latter, since the manual's figure is out of date."""
    for entry in PART5:
        assert "manual v1.0" in entry.source, entry.topic
