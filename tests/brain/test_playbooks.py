"""Playbook retrieval and the seeded library.

Retrieval is pure, so all of this runs without a database or the API.
"""
import pytest

from app.services.brain import playbooks as pb
from app.services.brain.constants import LeadIntent, ResponseMode, Stage
from app.services.brain.playbook_seed import SEED
from app.services.brain.writer import MODE_SPECS, ModeSpec, energy_max_chars, few_shot_messages


def _pb(slug, **kw):
    kw.setdefault("title", slug)
    return pb.Playbook(slug=slug, **kw)


# --- retrieval ---------------------------------------------------------------

def test_intent_beats_mode_only():
    generic = _pb("generic", mode="ACKNOWLEDGE")
    specific = _pb("specific", mode="ACKNOWLEDGE", intents=["gratitude"])
    chosen = pb.select([generic, specific], mode=ResponseMode.ACKNOWLEDGE,
                       intent=LeadIntent.GRATITUDE, stage=Stage.COLD)
    assert chosen.slug == "specific"


def test_playbook_for_another_intent_is_never_returned():
    """A playbook naming intents is about those conversations only.

    Returning the grief playbook for a thank-you would be worse than returning
    nothing, because its examples actively demonstrate the wrong reply.
    """
    grief = _pb("grief", mode="ACKNOWLEDGE", intents=["grief_or_stopped_trying"])
    assert pb.select([grief], mode=ResponseMode.ACKNOWLEDGE,
                     intent=LeadIntent.GRATITUDE, stage=Stage.COLD) is None


def test_wrong_mode_is_never_returned():
    celebrate = _pb("celebrate", mode="CELEBRATE", intents=["gratitude"])
    assert pb.select([celebrate], mode=ResponseMode.QUALIFY,
                     intent=LeadIntent.GRATITUDE, stage=Stage.COLD) is None


def test_triggers_break_a_tie_within_an_intent():
    plain = _pb("plain", intents=["general_fertility_question"])
    ivf = _pb("ivf", intents=["general_fertility_question"], triggers=[r"\bivf\b"])
    chosen = pb.select([plain, ivf], mode=ResponseMode.ANSWER,
                       intent=LeadIntent.GENERAL_FERTILITY_QUESTION, stage=Stage.COLD,
                       text="anything worth doing before my IVF?")
    assert chosen.slug == "ivf"


def test_inactive_and_other_language_are_excluded():
    off = _pb("off", intents=["gratitude"], active=False)
    es = _pb("es", intents=["gratitude"], language="es")
    assert pb.select([off, es], mode=ResponseMode.ACKNOWLEDGE,
                     intent=LeadIntent.GRATITUDE, stage=Stage.COLD) is None


def test_selection_is_deterministic_across_runs():
    a = _pb("aaa", intents=["gratitude"])
    b = _pb("bbb", intents=["gratitude"])
    picks = {pb.select([a, b], mode=ResponseMode.ACKNOWLEDGE,
                       intent=LeadIntent.GRATITUDE, stage=Stage.COLD).slug
             for _ in range(5)}
    assert picks == {"aaa"}


def test_malformed_trigger_does_not_break_a_live_turn():
    bad = _pb("bad", intents=["gratitude"], triggers=["([unclosed"])
    assert pb.select([bad], mode=ResponseMode.ACKNOWLEDGE,
                     intent=LeadIntent.GRATITUDE, stage=Stage.COLD,
                     text="([unclosed").slug == "bad"


# --- variation ---------------------------------------------------------------

def test_examples_rotate_per_lead():
    """Two people in the same situation must not get near-identical replies.

    The model leans hardest on the first exemplar, so which one leads is a cheap
    deterministic source of variation.
    """
    p = _pb("x", examples=[{"turns": [{"lead": str(i), "sonia": f"reply {i}"}]}
                           for i in range(3)])
    orders = {tuple(e["turns"][0]["sonia"] for e in pb.rotate_examples(p, uid))
              for uid in ("lead_a", "lead_b", "lead_c", "lead_d", "lead_e")}
    assert len(orders) > 1, "every lead sees the same exemplar order"


def test_rotation_is_stable_for_one_lead():
    p = _pb("x", examples=[{"turns": [{"lead": str(i), "sonia": str(i)}]} for i in range(3)])
    assert pb.rotate_examples(p, "lead_a") == pb.rotate_examples(p, "lead_a")


def test_as_messages_never_ends_on_a_lead_turn():
    p = _pb("x", examples=[{"turns": [{"lead": "hi", "sonia": "hey"}, {"lead": "?"}]}])
    messages = pb.as_messages(p.examples)
    assert messages[-1]["role"] == "assistant"


# --- what reaches the prompt --------------------------------------------------

def test_review_only_fields_never_reach_the_prompt():
    """Every prompt token is paid on every turn. These fields describe the
    pattern for Sonia rather than instructing the reply."""
    p = _pb("x", situation="S", goal="G",
            success_criteria="SHOULD-NOT-APPEAR", why_this_works="ALSO-NOT",
            decision_outcome="NOR-THIS", information_that_matters="NOR-THAT",
            conversation_state="NOR-THIS-EITHER")
    block = pb.prompt_block(p)
    assert "S" in block and "G" in block
    for absent in ("SHOULD-NOT-APPEAR", "ALSO-NOT", "NOR-THIS", "NOR-THAT"):
        assert absent not in block


def test_no_playbook_yields_no_block():
    assert pb.prompt_block(None) == ""


def test_playbook_examples_reach_modes_that_refuse_generic_few_shots():
    """CELEBRATE runs with no few-shots because every transcript in few_shots/
    is a qualification conversation ending in a booking link. Its playbook
    examples must still get through, or it has no exemplar at all."""
    spec = MODE_SPECS[ResponseMode.CELEBRATE]
    assert spec.few_shots is False
    p = _pb("x", examples=[{"turns": [{"lead": "I'm pregnant!", "sonia": "congratulations!"}]}])
    messages = few_shot_messages(spec, "", allow_urls=[], playbook=p)
    assert [m["content"] for m in messages] == ["I'm pregnant!", "congratulations!"]


def test_playbook_examples_are_link_truncated_when_links_are_not_allowed():
    spec = MODE_SPECS[ResponseMode.ACKNOWLEDGE]
    p = _pb("x", examples=[{"turns": [
        {"lead": "hi", "sonia": "hey"},
        {"lead": "how do I start?", "sonia": "book here https://example.com/free-call"},
    ]}])
    messages = few_shot_messages(spec, "", allow_urls=[], playbook=p)
    assert not any("http" in m["content"] for m in messages)


# --- energy matching ----------------------------------------------------------

def test_short_message_gets_a_short_reply_budget():
    """Sonia 6.6: do not answer one short sentence with an essay."""
    spec = MODE_SPECS[ResponseMode.QUALIFY]
    assert energy_max_chars(spec, ["I'm preparing for IVF in September"]) < spec.max_chars


def test_long_message_gets_the_full_budget():
    spec = MODE_SPECS[ResponseMode.QUALIFY]
    assert energy_max_chars(spec, ["x" * 400]) == spec.max_chars


def test_link_modes_keep_a_workable_floor():
    """A reply carrying a link cannot be two sentences."""
    spec = MODE_SPECS[ResponseMode.BOOK]
    assert energy_max_chars(spec, ["ok"]) >= 320


# --- the seeded library -------------------------------------------------------

def test_seed_slugs_are_unique():
    slugs = [p.slug for p in SEED]
    assert len(slugs) == len(set(slugs))


@pytest.mark.parametrize("playbook", SEED, ids=lambda p: p.slug)
def test_seed_entry_is_usable(playbook):
    assert playbook.examples, f"{playbook.slug} has no examples, so it teaches nothing"
    assert playbook.situation and playbook.goal
    assert playbook.source, "every entry must say where it came from"
    for intent in playbook.intents:
        LeadIntent(intent)          # raises on a typo
    for stage in playbook.stages:
        Stage(stage)
    if playbook.mode:
        ResponseMode(playbook.mode)


@pytest.mark.parametrize("playbook", SEED, ids=lambda p: p.slug)
def test_seed_examples_obey_the_house_style(playbook):
    for example in playbook.examples:
        for turn in example["turns"]:
            reply = turn.get("sonia") or ""
            assert "—" not in reply and "–" not in reply, "no em-dashes"
            assert "http" not in reply, (
                "an exemplar containing a link teaches the model to send one; "
                "that prior is what flooded the calendar in Gen 2"
            )


@pytest.mark.parametrize(
    "playbook", [p for p in SEED if p.mode in ("CELEBRATE", "ACKNOWLEDGE",
                                               "RESOURCE", "HONEST_DECLINE")],
    ids=lambda p: p.slug)
def test_no_question_modes_have_no_question_in_their_examples(playbook):
    """An exemplar ending in a question teaches exactly the habit Sonia asked us
    to remove."""
    for example in playbook.examples:
        for turn in example["turns"]:
            assert "?" not in (turn.get("sonia") or ""), playbook.slug


def test_the_never_qualify_modes_all_have_a_playbook():
    """These are the conversations that had no material anywhere in the repo."""
    covered = {p.mode for p in SEED}
    assert {"CELEBRATE", "ACKNOWLEDGE", "HONEST_DECLINE"} <= covered


# --- teaching the library from a reviewed turn --------------------------------
# Sonia: "The biggest improvements will come from building the Conversation
# Playbook Library with real, edited conversations." /admin/shadow has a button
# for it; this is the rule behind the button.

def test_a_reviewed_exchange_is_added_not_substituted():
    """Her existing examples are the library. Promoting must never replace them."""
    from app.repositories.playbook import next_examples

    existing = [{"turns": [{"lead": "a", "sonia": "b"}]}]
    updated = next_examples(existing, "I'm pregnant!", "congratulations!")
    assert len(updated) == 2
    assert updated[0] == existing[0]
    assert updated[1]["turns"][0]["sonia"] == "congratulations!"


def test_the_original_list_is_not_mutated():
    """The JSON column has to be reassigned or SQLAlchemy never writes it."""
    from app.repositories.playbook import next_examples

    existing = [{"turns": [{"lead": "a", "sonia": "b"}]}]
    next_examples(existing, "x", "y")
    assert len(existing) == 1


@pytest.mark.parametrize("lead,sonia", [("", "reply"), ("lead", ""), ("  ", "  ")])
def test_a_half_empty_exchange_is_refused(lead, sonia):
    from app.repositories.playbook import next_examples

    assert next_examples([], lead, sonia) is None


def test_a_promoted_example_is_retrievable_and_usable():
    """Round trip: what the button saves must be what retrieval can read."""
    from app.repositories.playbook import next_examples

    examples = next_examples([], "I just got my positive test!", "congratulations!")
    p = _pb("x", examples=examples)
    assert pb.as_messages(pb.rotate_examples(p, "lead_a")) == [
        {"role": "user", "content": "I just got my positive test!"},
        {"role": "assistant", "content": "congratulations!"},
    ]


# --- priority signal (manual 2A section 9) ------------------------------------

def test_a_dated_treatment_plan_counts_as_priority():
    """Manual 2A section 9: "preparing for treatment soon" is a strong-priority
    signal on its own. It arrives as strong_readiness, which classify.py is told
    explicitly to set for a booked or imminent cycle."""
    from app.services.brain.gates import _priority_ok

    assert _priority_ok({"strong_readiness": True}) is True


def test_treatment_history_alone_does_not_count():
    """Tried and reverted: reading priority off treatment_path cannot tell
    "preparing for IVF in September" from "2 failed IUIs two years ago", so it
    skipped the priority question for anyone with any treatment history. A
    wrongly-booked call is far more costly than a wrongly-asked question."""
    from app.services.brain.gates import _priority_ok

    assert _priority_ok({"treatment_path": "ivf"}) is False
    assert _priority_ok({"treatment_path": "iui"}) is False


def test_her_own_score_decides_when_she_gave_one():
    from app.services.brain.gates import _priority_ok

    assert _priority_ok({"priority_score": 9}) is True
    assert _priority_ok({"priority_score": 5}) is False
