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


def test_pricing_figure_is_not_live():
    """The manual says $1,500-$10,000; the live config says $14,000. That number
    is quoted to real prospects, so it waits for Sonia rather than shipping on a
    document's say-so."""
    pricing = next(e for e in PART5 if e.topic == "pricing_range")
    assert pricing.active is False
    assert "CONFLICTS" in pricing.source


def test_no_active_entry_states_a_price():
    for entry in SEED:
        if entry.active:
            assert "$" not in entry.content, (
                f"{entry.kind}/{entry.topic} states a price while active; the "
                f"figure is contested between the manual and the live config"
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
    for entry in PART5:
        assert entry.source.startswith("manual v1.0")
