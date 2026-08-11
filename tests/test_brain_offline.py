"""Everything about the brain that can be checked without an API key.

Three things are being protected here:

  * the library is well-formed and states no fact of its own, every price, link and credential
    reaches a conversation through config, so a change in /admin/config actually takes effect;
  * the gates behave, because they are the whole safety model. When a gate says no, the booking
    block never reaches the prompt, so these assertions are the thing standing between a
    51-year-old and a booking link;
  * selection picks the right conversations, including the three cases the old regex table got
    wrong.
"""
import os
import re

import pytest

from app.services import dossier, prompts
from app.services.few_shots import load_few_shot_scenarios, render_examples, select_playbooks

FEW_SHOTS = load_few_shot_scenarios("few_shots")

CFG = {
    "kb_about": "I'm Sonia Ribas, a fertility coach with 16 years of experience.",
    "kb_program": "One-to-one fertility coaching.",
    "kb_pricing": "Programs range from approximately $1,500 to $14,000.",
    "kb_boundaries": "I do not provide IVF.",
    "kb_team": "Natalia texts before the appointment.",
    "kb_faq": "Are you a doctor? No.",
    "kb_free_resource": "The masterclass is free.",
    "booking_link": "https://example.test/free-call",
    "masterclass_link": "https://example.test/watch-replay",
    "price_range": "$1,500 to $14,000",
    "years_experience": "16 years",
    "babies_welcomed": "735",
}


# ── The library ──────────────────────────────────────────────────────────────

def test_every_playbook_is_well_formed():
    assert len(FEW_SHOTS) > 30
    for name, pb in FEW_SHOTS.items():
        assert pb.intent, f"{name} declares no intent"
        assert pb.tags, f"{name} declares no tags"
        assert pb.conversations, f"{name} has no conversation"
        for arc in pb.conversations:
            assert "Lead:" in arc and "Sonia:" in arc, f"{name} has an arc with no dialogue"


def test_conversations_are_complete_not_fragments():
    """A file is whole conversations, not isolated question-and-answer pairs.

    A couple of arcs are legitimately short, celebrating a pregnancy takes two messages, not
    eight, so the floor is low and the body of the library has to be well above it.
    """
    lengths = []
    for name, pb in FEW_SHOTS.items():
        for arc in pb.conversations:
            turns = arc.count("Sonia:")
            assert turns >= 2, f"{name} has an arc with only {turns} replies. That is a fragment"
            lengths.append(turns)
    lengths.sort()
    assert lengths[len(lengths) // 2] >= 5, f"median arc is only {lengths[len(lengths) // 2]} replies"


def test_endings_are_not_all_booking_links():
    """The old library ended 17 of 18 conversations with the link, which is what taught the
    model to funnel everything toward the calendar. Counted per arc, since a two-arc file
    typically books in one and not the other."""
    arcs = [arc for pb in FEW_SHOTS.values() for arc in pb.conversations]
    books = sum(1 for arc in arcs if "{{booking_link}}" in arc)
    assert books / len(arcs) < 0.55, (
        f"{books} of {len(arcs)} conversations end in a booking link"
    )


def test_every_playbook_survives_a_non_booking_turn():
    """A booking-only file disappears from most of the conversation.

    `Playbook.render` drops arcs containing the link when the gate says no link, and
    `select_playbooks` discards anything that renders empty. Since most turns cannot offer a call,
    a file whose every arc ends in the link is absent exactly when her situation comes up, and the
    writer falls back to whichever loosely related file happens to carry a non-booking arc.
    """
    vanished = [
        name for name, pb in FEW_SHOTS.items()
        if pb.conversations and not pb.render(allow_booking=False)
    ]
    assert vanished == ["ready_to_book"], (
        f"{vanished} render empty on a non-booking turn. Give each one an arc that ends in an "
        f"honest answer, a free resource or a respectful no. `ready_to_book` is the one exception."
    )


def test_no_file_states_a_fact_of_its_own():
    """No literal URL or price anywhere, placeholders only, resolved from config."""
    offenders = []
    for directory in ("few_shots", "prompts"):
        for filename in sorted(os.listdir(directory)):
            path = os.path.join(directory, filename)
            if not os.path.isfile(path) or filename.startswith("."):
                continue
            text = open(path, encoding="utf-8").read()
            hits = re.findall(r"https?://\S+", text) + re.findall(r"\$\s?[\d,]{3,}", text)
            if hits:
                offenders.append((path, hits[:3]))
    assert not offenders, f"literal facts found: {offenders}"


def test_first_person_only():
    """Prospect-facing text is always 'I', never 'Sonia' in the third person."""
    third_person = re.compile(r"\bSonia's\b|\bSonia (is|was|has|will|can|does|would)\b")
    for name, pb in FEW_SHOTS.items():
        for arc in pb.conversations:
            for line in arc.splitlines():
                if line.startswith("Sonia:"):
                    assert not third_person.search(line), f"{name}: third-person Sonia in {line!r}"


# ── The dossier ──────────────────────────────────────────────────────────────

def test_merge_accumulates_lists_and_never_forgets_flags():
    state = dossier.merge(None, {
        "slots": {"age": 38, "diagnoses": ["PCOS"]},
        "flags": {"refuses_paid_coaching": True},
    })
    state = dossier.merge(state, {"slots": {"diagnoses": ["low AMH"], "time_trying": "2 years"}})

    assert state["slots"]["age"] == 38
    assert state["slots"]["diagnoses"] == ["PCOS", "low AMH"]
    assert state["slots"]["time_trying"] == "2 years"
    # A later message that simply does not mention it must not quietly clear it.
    assert state["flags"]["refuses_paid_coaching"] is True
    assert state["counters"]["turns"] == 2


def test_merge_does_not_duplicate_a_restated_diagnosis():
    state = dossier.merge(None, {"slots": {"diagnoses": ["PCOS"]}})
    state = dossier.merge(state, {"slots": {"diagnoses": ["pcos "]}})
    assert state["slots"]["diagnoses"] == ["PCOS"]


def test_dossier_renders_what_she_said():
    state = dossier.merge(None, {"slots": {"age": 34, "time_trying": "18 months"}})
    rendered = dossier.render(state)
    assert "34" in rendered and "18 months" in rendered
    assert "never ask" in rendered.lower()


# ── The gates ────────────────────────────────────────────────────────────────

def _state(slots=None, flags=None, phase=None, turns=2):
    """A lead mid-conversation by default, a first exchange is gated on its own account."""
    state = dossier.merge(None, {"slots": slots or {}, "flags": flags or {}})
    state["counters"]["turns"] = turns
    state["phase"] = phase
    return state


QUALIFIED = {"age": 36, "time_trying": "2 years", "pregnancy_priority": "high"}


def test_a_qualified_lead_gets_the_booking_block():
    gate = dossier.gate(_state(QUALIFIED), {"intent": "warm_prospect"})
    assert gate.allow_booking
    assert "booking" in gate.blocks


def test_no_link_on_the_very_first_message():
    """Everything known from one message is still a first message, not an understanding."""
    gate = dossier.gate(_state(QUALIFIED, turns=1), {"intent": "fertility_question"})
    assert not gate.allow_booking
    assert gate.block_reason == "first_exchange"


def test_someone_who_opens_ready_is_not_made_to_wait():
    gate = dossier.gate(_state(QUALIFIED, turns=1), {"intent": "warm_prospect"})
    assert gate.allow_booking


@pytest.mark.parametrize("slots,flags,why", [
    ({**QUALIFIED, "age": 51}, {}, "over 48"),
    (QUALIFIED, {"structural": "no_uterus"}, "no uterus"),
    (QUALIFIED, {"structural": "menopause"}, "menopause"),
    (QUALIFIED, {"structural": "both_tubes", "wants_natural_only": True}, "both tubes, natural only"),
    (QUALIFIED, {"structural": "unclear_tubal"}, "tubal status not yet clarified"),
    (QUALIFIED, {"refuses_paid_coaching": True}, "will not pay"),
    (QUALIFIED, {"demands_guarantee": True}, "wants a guarantee"),
    (QUALIFIED, {"wants_unprovided_service": True}, "out of scope"),
    (QUALIFIED, {"recent_loss": True}, "grieving"),
    ({**QUALIFIED, "pregnancy_priority": "low"}, {}, "not a priority"),
    ({"age": 34}, {}, "not enough context yet"),
])
def test_the_booking_block_is_withheld(slots, flags, why):
    gate = dossier.gate(_state(slots, flags), {"intent": "fertility_question"})
    assert not gate.allow_booking, why
    assert "booking" not in gate.blocks, f"link would still reach the prompt: {why}"


def test_both_tubes_with_ivf_openness_can_still_book():
    gate = dossier.gate(
        _state(QUALIFIED, {"structural": "both_tubes", "open_to_ivf": True}),
        {"intent": "ivf_question"},
    )
    assert gate.allow_booking


@pytest.mark.parametrize("flags,intent,reason", [
    ({"needs_human": True}, "fertility_question", "needs_human"),
    ({"requested_medication": True}, "advice_request", "requested_medication"),
    ({"requested_surgery_advice": True}, "advice_request", "requested_surgery_advice"),
    ({"is_existing_client": True}, "existing_client", "is_existing_client"),
    ({"is_former_client": True}, "former_client", "is_former_client"),
    ({"structural": "unclear_menopause"}, "fertility_question", "menopause_unclear"),
    ({"abusive": True}, "spam_or_aggression", "abusive"),
    ({}, "complaint", "complaint"),
    ({}, "collaboration", "collaboration"),
])
def test_handovers_are_silent(flags, intent, reason):
    """Every handover pauses, and by default the lead is sent nothing at all."""
    gate = dossier.gate(_state(QUALIFIED, flags), {"intent": intent})
    assert gate.escalate and gate.escalate_reason == reason
    assert not gate.allow_booking
    assert gate.silent and not gate.handover_message


@pytest.mark.parametrize("flags,reason,key", [
    ({"crisis": True}, "crisis", "handover_message_crisis"),
    ({"urgent_medical": True}, "urgent_medical", "handover_message_urgent_medical"),
    ({"asked_for_human": True}, "asked_for_human", "handover_message_team"),
    ({"asked_if_ai": True}, "asked_if_ai", "handover_message_team"),
])
def test_the_four_handovers_that_send_a_fixed_line(flags, reason, key):
    """Silence would be its own harm here, so these carry a config key instead."""
    gate = dossier.gate(_state(QUALIFIED, flags), {"intent": "fertility_question"})
    assert gate.escalate and gate.escalate_reason == reason
    assert gate.handover_message == key and not gate.silent


def test_safety_flags_outrank_everything_else():
    """Crisis names the reason even when three other handover flags are also set."""
    flags = {"crisis": True, "asked_for_human": True, "requested_medication": True}
    gate = dossier.gate(_state(QUALIFIED, flags), {"intent": "complaint"})
    assert gate.escalate_reason == "crisis"


def test_a_handover_turn_renders_no_knowledge_blocks():
    """The writer is never called, so there is nothing for a block to be rendered into."""
    gate = dossier.gate(_state(QUALIFIED, {"needs_human": True}), {"intent": "fertility_question"})
    assert gate.blocks == set()


def test_age_in_the_review_band_escalates_rather_than_rejecting():
    gate = dossier.gate(_state({**QUALIFIED, "age": 47}), {"intent": "fertility_question"})
    assert gate.escalate and gate.escalate_reason == "age_needs_review"


def test_unsupported_language_goes_to_a_person():
    state = dossier.merge(None, {"language": "other", "slots": QUALIFIED})
    gate = dossier.gate(state, {"intent": "new_prospect"})
    assert gate.escalate and gate.escalate_reason == "language_not_supported"


def test_post_booking_block_only_after_the_link_went_out():
    assert "post_booking" not in dossier.gate(_state(QUALIFIED), {"intent": "warm_prospect"}).blocks
    later = dossier.gate(_state(QUALIFIED, phase=dossier.LINK_SENT), {"intent": "warm_prospect"})
    assert "post_booking" in later.blocks


# ── Selection ────────────────────────────────────────────────────────────────

def _picked(**kwargs):
    kwargs.setdefault("language", "en")
    return [pb.name for pb in select_playbooks(FEW_SHOTS, **kwargs)]


@pytest.mark.parametrize("intent,tags,expected", [
    # The three the old regex table got wrong.
    ("ivf_question", ["ivf_prep"], "ivf_prep"),            # matched ivf_failed on the word "ivf"
    ("price_question", ["affordability"], "cant_afford"),  # matched partner_hesitation on "afford"
    ("price_question", ["pricing"], "pricing"),            # was in _SKIP and never loaded at all
    # Ordinary routing.
    ("fertility_question", ["low_amh"], "low_amh"),
    ("fertility_question", ["tubal"], "blocked_tubes"),
    ("advice_request", ["lab_request"], "lab_interpretation"),
    ("grief_or_loss", ["loss_recent"], "pregnancy_loss_fresh"),
    ("pregnancy_announcement", ["celebration"], "announcements"),
    ("existing_client", ["human_requested"], "existing_or_former_client"),
])
def test_selection_picks_the_right_conversation(intent, tags, expected):
    assert expected in _picked(intent=intent, tags=tags)


def test_spanish_only_surfaces_in_a_spanish_conversation():
    assert not any(n.endswith("_es") for n in _picked(intent="price_question", tags=["pricing"]))
    assert "pricing_es" in _picked(intent="price_question", tags=["pricing"], language="es")


@pytest.mark.parametrize("slots,flags,read_tags,intent,expected_gate,expected_first", [
    # A 38-year-old frightened of time gets her own conversation, not the one written for 51.
    # and age plus time trying is not yet enough understanding to invite her to a call.
    ({"age": 38, "time_trying": "4 months"}, {}, ["low_amh", "fear_of_time"],
     "fertility_question", "no-link", "low_amh"),
    ({**QUALIFIED, "diagnoses": ["low AMH"]}, {}, ["low_amh"],
     "fertility_question", "link", "low_amh"),
    ({"age": 51, "time_trying": "2 years", "pregnancy_priority": "high"}, {}, ["fear_of_time"],
     "fertility_question", "no-link", "over_48"),
    (QUALIFIED, {"structural": "unclear_tubal"}, ["tubal"],
     "fertility_question", "no-link", "blocked_tubes"),
    (QUALIFIED, {"requested_lab_interpretation": True}, ["lab_request"],
     "advice_request", "no-link", "lab_interpretation"),
    (QUALIFIED, {"wants_unprovided_service": True}, [],
     "not_a_fit", "no-link", "wants_services_i_dont_provide"),
    (QUALIFIED, {"demands_guarantee": True}, [],
     "program_question", "no-link", "guarantee_demand"),
    (QUALIFIED, {"recent_loss": True}, ["loss_recent"],
     "grief_or_loss", "no-link", "pregnancy_loss_fresh"),
])
def test_the_gate_pulls_the_right_conversation(
    slots, flags, read_tags, intent, expected_gate, expected_first
):
    """The boundary conversations are selected by the fact that tripped the gate, so the writer
    is always shown the arc that matches the situation it is actually in."""
    g = dossier.gate(_state(slots, flags), {"intent": intent})
    assert ("link" if g.allow_booking else "no-link") == expected_gate
    picked = _picked(intent=intent, tags=read_tags + g.tags, allow_booking=g.allow_booking)
    assert picked[0] == expected_first, picked


def test_post_booking_conversation_only_appears_after_a_booking():
    assert "post_booking_email" not in _picked(intent="warm_prospect", tags=["ready_to_book"])
    later = dossier.gate(_state(QUALIFIED, phase=dossier.LINK_SENT), {"intent": "warm_prospect"})
    assert "post_booking_email" in _picked(intent="warm_prospect", tags=later.tags)


def test_a_gated_turn_is_never_shown_a_booking_arc():
    picked = select_playbooks(
        FEW_SHOTS, intent="fertility_question", tags=["low_amh"], allow_booking=False,
    )
    rendered = render_examples(picked, allow_booking=False, values=CFG)
    assert rendered
    assert CFG["booking_link"] not in rendered


def test_examples_resolve_their_placeholders():
    """The writer must never be shown a literal `{{booking_link}}`. It would send it."""
    picked = select_playbooks(FEW_SHOTS, intent="price_question", tags=["pricing"])
    rendered = render_examples(picked, allow_booking=True, values=CFG)
    assert "{{" not in rendered
    assert CFG["price_range"] in rendered


# ── Prompt assembly ──────────────────────────────────────────────────────────

def test_the_link_is_absent_from_the_prompt_when_the_gate_says_no():
    gated = prompts.build_write_prompt(CFG, {"pricing", "free_resource"})
    assert CFG["booking_link"] not in gated

    allowed = prompts.build_write_prompt(CFG, {"pricing", "free_resource", "booking"})
    assert CFG["booking_link"] in allowed


def test_no_placeholder_survives_into_the_prompt():
    built = prompts.build_write_prompt(CFG, {"pricing", "booking", "free_resource", "post_booking"})
    assert "{{" not in built and "[[BLOCK" not in built


def test_the_prompt_carries_the_facts_and_the_hard_boundaries():
    built = prompts.build_write_prompt(CFG, {"pricing", "booking", "free_resource"})
    for fact in ("16 years", "735", "$1,500 to $14,000"):
        assert fact in built
    for rule in ("both tubes", "Never say", "first person"):
        assert rule.lower() in built.lower()


def test_missing_config_collapses_rather_than_leaking_braces():
    built = prompts.build_write_prompt({}, {"booking"})
    assert "{{" not in built
