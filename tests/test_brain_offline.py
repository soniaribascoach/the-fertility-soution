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

from app.services import brain, cta, dossier, message_splitter, prompts, reader
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
    """Tags are the requirement; an intent is optional.

    Boundary conversations are selected by the tag the gate attaches to the fact that triggered it
    (`_REASON_TAGS` in `dossier.py`), not by whatever intent the reader happened to return, so
    `blocked_tubes`, `no_uterus`, `over_48`, `post_booking_email` and their `_es` twins
    deliberately declare no intent. Tags without an intent is a complete declaration; an intent
    without tags is not, because `score_playbook` never lets intent alone earn a slot.
    """
    assert len(FEW_SHOTS) > 30
    for name, pb in FEW_SHOTS.items():
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
    assert vanished == [], (
        f"{vanished} render empty on a non-booking turn. Give each one an arc that ends in an "
        f"honest answer, a free resource or a respectful no."
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


def test_no_link_until_she_has_said_how_old_she_is():
    """Over 48 is a hard boundary, and it can only be applied to an age she actually gave.

    Everything else about this lead is known and none of it decides anything. She could be 52 and
    the reader is forbidden from guessing, so the boundary is enforceable only by refusing to
    invite anyone whose age has never been asked.
    """
    known_but_ageless = {
        "time_trying": "3 years", "conceiving_mode": "naturally",
        "pregnancy_priority": "high", "partner_status": "husband",
    }
    gate = dossier.gate(_state(known_but_ageless), {"intent": "fertility_question"})
    assert not gate.allow_booking
    assert gate.block_reason == "age_unknown"
    assert "booking" not in gate.blocks


def test_saying_she_is_ready_does_not_stand_in_for_her_age():
    """The warm-prospect bypass skips the first-exchange wait, not the boundary."""
    gate = dossier.gate(_state({"pregnancy_priority": "high"}, turns=1), {"intent": "warm_prospect"})
    assert not gate.allow_booking
    assert gate.block_reason == "age_unknown"


def test_age_is_the_first_thing_the_writer_is_told_to_ask_for():
    """Order in DISCOVERY is the priority the writer is given. Partner status comes last."""
    missing = dossier.missing_facts(dossier.empty_state())
    assert missing[0] == "how old she is"
    assert "partner" in missing[-1]

    known = _state({"age": 36})
    assert "how old she is" not in dossier.missing_facts(known)


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
    (QUALIFIED, {"currently_pregnant": True}, "already pregnant"),
    ({**QUALIFIED, "pregnancy_priority": "low"}, {}, "not a priority"),
    ({"age": 34}, {}, "not enough context yet"),
])
def test_the_booking_block_is_withheld(slots, flags, why):
    gate = dossier.gate(_state(slots, flags), {"intent": "fertility_question", "flags": flags})
    assert not gate.allow_booking, why
    assert "booking" not in gate.blocks, f"link would still reach the prompt: {why}"


def test_asking_sonia_for_a_service_she_does_not_provide_shuts_the_link_for_that_turn():
    read = {"intent": "not_a_fit", "flags": {"wants_unprovided_service": True}}
    gate = dossier.gate(_state(QUALIFIED), read)
    assert not gate.allow_booking
    assert gate.block_reason == "out_of_scope_request"
    assert "booking" not in gate.blocks


def test_a_service_she_asked_for_once_does_not_shut_the_link_for_the_rest_of_the_conversation():
    """The reason run two of the m_runs corpus answered four messages with four refusals.

    "I'm planning IVF in a month or two" is a sentence half of her audience opens with, and one
    reader misfire on it used to set a flag nothing could clear: every later turn was gated
    `out_of_scope_request` and told to name what she does not provide, so a woman who then asked
    what a fertility coach does, how to enroll and what her next step was got three more sentences
    about what does not happen here and was never asked a single question.
    """
    state = dossier.merge(_state(QUALIFIED), {
        "intent": "not_a_fit", "flags": {"wants_unprovided_service": True},
    })
    later = dossier.gate(state, {"intent": "program_question"})
    assert later.allow_booking
    assert later.block_reason == ""


def test_a_pregnancy_stays_known_after_the_turn_that_announced_it():
    """The reader reports a live pregnancy as an intent, which describes one turn.

    She announces on turn 1 and asks what to eat on turn 4, by which point the intent has moved on.
    Round 5 left the link open on exactly that turn and the reply quoted the price range to her.
    """
    state = dossier.merge(_state(QUALIFIED), {"intent": "pregnancy_announcement"})
    assert state["flags"]["currently_pregnant"]

    later = dossier.merge(state, {"intent": "fertility_question"})
    gate = dossier.gate(later, {"intent": "fertility_question"})
    assert not gate.allow_booking
    assert gate.block_reason == "currently_pregnant"


@pytest.mark.parametrize("value", ["unstated", "not stated", "unknown", "N/A", "none", ""])
def test_a_slot_the_reader_filled_with_a_shrug_is_not_a_fact(value):
    """"partner_status: unstated" is the absence of a fact wearing the costume of one.

    It counted toward the three-slot threshold that decides whether an invitation is honest, so a
    booking could turn on the reader having written the word "unstated" rather than omitting the
    key, and it rendered into the writer's dossier under "what she has already told me".
    """
    state = dossier.merge(None, {"intent": "new_prospect", "slots": {
        "age": 34, "time_trying": "2 years", "partner_status": value,
    }})
    assert "partner_status" not in state["slots"]

    gate = dossier.gate(state, {"intent": "fertility_question"})
    assert not gate.allow_booking
    assert gate.block_reason == "not_enough_context"
    assert "not stated" not in dossier.render(state).lower()


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
    is always shown the arc that matches the situation it is actually in.

    The flags go to the read as well as to the state, because this is the turn they arrived on and
    one of them, `wants_unprovided_service`, is now read from the turn rather than from the dossier.
    """
    g = dossier.gate(_state(slots, flags), {"intent": intent, "flags": flags})
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


# ── Dashes, the one thing that is fixed after the writer, not before ──────────
#
# Five rounds of manual testing put an em dash in front of a lead in about one conversation in
# four, including the first line a woman announcing a pregnancy read. The rule is in `40_voice.md`
# and in `60_contract.md` and it has never reached zero, so the substitution is mechanical. These
# tests are the argument that it is safe: nothing about a decision, a boundary or a link changes.

REAL_DASHES = [
    # Every one of these was produced by the writer during round 5 and sent to a scripted lead.
    ("Proper reading requires the full context\u2014your age, cycle details, symptoms.",
     "Proper reading requires the full context, your age, cycle details, symptoms."),
    ("It’s not just about her body\u2014both partners contribute.",
     "It’s not just about her body, both partners contribute."),
    ("Enjoy this moment\u2014it’s truly special.",
     "Enjoy this moment, it’s truly special."),
    ("Two years trying, low AMH, natural approach still\u2014 that’s where I’d pick up.",
     "Two years trying, low AMH, natural approach still, that’s where I’d pick up."),
    ("That’s what I’d focus on\u2014finding what’s been missed\u2014and building a plan.",
     "That’s what I’d focus on, finding what’s been missed, and building a plan."),
]


@pytest.mark.parametrize("written,sent", REAL_DASHES)
def test_no_lead_is_ever_sent_a_dash(written, sent):
    assert message_splitter.strip_dashes(written) == sent


@pytest.mark.parametrize("text", [
    "whole-body approach for low-AMH and thirty-six year olds",
    "Programs range from $1,500 to $14,000.",
    "No dashes here at all.",
])
def test_text_without_a_dash_is_returned_untouched(text):
    assert message_splitter.strip_dashes(text) == text


def test_a_range_becomes_the_word_and_not_a_comma():
    assert message_splitter.strip_dashes("$1,500\u2013$14,000") == "$1,500 to $14,000"
    assert message_splitter.strip_dashes("ages 35\u201340") == "ages 35 to 40"


def test_the_paragraph_break_the_splitter_needs_survives():
    cleaned = message_splitter.strip_dashes("Para one\u2014\n\nPara two here.")
    assert cleaned == "Para one\n\nPara two here."
    assert message_splitter.split_reply(cleaned, natural=False) == ["Para one", "Para two here."]


def test_a_dash_after_punctuation_does_not_double_it():
    assert message_splitter.strip_dashes("yes,\u2014and then") == "yes, and then"


def test_the_link_and_the_price_survive_the_substitution():
    reply = (
        "The program ranges from $1,500 to $14,000\u2014it depends on the support you need.\n\n"
        "https://example.test/free-call"
    )
    cleaned = message_splitter.strip_dashes(reply)
    assert "https://example.test/free-call" in cleaned
    assert "$1,500 to $14,000" in cleaned
    assert "\u2014" not in cleaned


# ── The second opinion on an unsupported language ────────────────────────────
#
# `language: "other"` sets `needs_human`, and that handover sends nothing at all. It is the only
# field in the extraction that ends a conversation silently on one sample, and measured on the
# round 5 corpus the extractor returns it for plain Spanish about 1 time in 10. A Spanish-speaking
# lead who trips that coin flip simply stops being answered.

class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeUsage:
    prompt_tokens = 10
    completion_tokens = 5


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class _FakeCompletions:
    """Replies to each call in turn; the last reply is repeated if more calls arrive."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._replies[min(len(self.calls) - 1, len(self._replies) - 1)])


class _FakeClient:
    def __init__(self, *replies):
        self.completions = _FakeCompletions(replies)
        self.chat = self

    @property
    def calls(self):
        return self.completions.calls


# `read_turn` calls in this order: the extraction, the narrow safety read, and the language
# question only when the extraction said `other`.
NO_TRIGGERS = '{"triggers": []}'


_OTHER = '{"intent": "new_prospect", "language": "other", "flags": {"needs_human": true}}'


async def test_a_second_opinion_rescues_a_spanish_lead_read_as_unsupported():
    client = _FakeClient(_OTHER, NO_TRIGGERS, "es")
    read, usage = await reader.read_turn(
        client, [{"role": "user", "content": "me dijeron que tengo baja reserva ovarica"}],
        model="gpt-4.1-mini",
    )

    assert read["language"] == "es"
    # The flag has to go with the answer that produced it: `70_read.md` asks for `needs_human` on
    # the same line it asks for `other`, and flags are sticky, so leaving it set would drop her
    # anyway through a different field.
    assert "needs_human" not in read["flags"]
    assert not dossier.gate(dossier.merge(None, read), read).escalate
    assert usage["prompt_tokens"] == 30, "every call should be paid for"


async def test_a_confirmed_third_language_still_goes_to_a_person():
    client = _FakeClient(_OTHER, NO_TRIGGERS, "other")
    read, _ = await reader.read_turn(
        client, [{"role": "user", "content": "posso escrever em portugues?"}], model="gpt-4.1-mini",
    )

    assert read["language"] == "other"
    gate = dossier.gate(dossier.merge(None, read), read)
    assert gate.escalate and gate.escalate_reason == "language_not_supported"


async def test_spanish_is_confirmed_because_portuguese_looks_like_it():
    client = _FakeClient('{"intent": "new_prospect", "language": "es"}', NO_TRIGGERS, "es")
    read, _ = await reader.read_turn(
        client, [{"role": "user", "content": "hola"}], model="gpt-4.1-mini",
    )

    assert read["language"] == "es"
    assert len(client.calls) == 3, "extraction, safety read, and the language question"


async def test_only_the_message_she_just_sent_decides_the_language():
    """Two ways of getting this wrong, and the fix for both is the same slice of the transcript.

    Sonia replies in the language she was written to in, so feeding her English reply in lets one
    of our own messages argue against the woman it was answering. And her older messages outvote
    her newest one: on the run 12 transcript the three English messages before the switch beat the
    Portuguese one she had just sent, and she was answered in a mixture of Spanish and Portuguese.
    """
    client = _FakeClient(_OTHER, NO_TRIGGERS, "es")
    await reader.read_turn(client, [
        {"role": "user", "content": "how much money for you help"},
        {"role": "assistant", "content": "Hello, how can I help you today?"},
        {"role": "user", "content": "posso escrever em portugues?"},
    ], model="gpt-4.1-mini")

    asked = client.calls[2]["messages"][-1]["content"]
    assert asked == "posso escrever em portugues?"
    assert "how much money" not in asked
    assert "how can I help you" not in asked


# ── The education spiral ─────────────────────────────────────────────────────

def _asked(state, intent, slots=None):
    return dossier.merge(state, {"intent": intent, "slots": slots or {}})


def test_general_questions_are_counted_across_turns():
    state = None
    for _ in range(4):
        state = _asked(state, "free_info_request")
    assert state["counters"]["teaching"] == 4


def test_a_question_that_says_something_about_her_is_not_a_general_one():
    state = _asked(_asked(None, "free_info_request"), "free_info_request")
    assert state["counters"]["teaching"] == 2

    state = _asked(state, "fertility_question", {"age": 34})
    assert state["counters"]["teaching"] == 0, "she told us something, the spiral restarted"


def test_asking_about_herself_resets_the_count():
    state = _asked(_asked(_asked(None, "free_info_request"), "free_info_request"), "warm_prospect")
    assert state["counters"]["teaching"] == 0


def test_restating_a_fact_we_already_hold_does_not_reset_the_count():
    """Six turns in she mentions her PCOS again. That is not new information about her."""
    state = dossier.merge(None, {"intent": "new_prospect", "slots": {"age": 34}})
    state = _asked(state, "free_info_request")
    state = _asked(state, "free_info_request", {"age": 34})
    assert state["counters"]["teaching"] == 2


def test_the_writer_is_told_the_number_rather_than_the_rule():
    state = None
    for _ in range(3):
        state = _asked(state, "free_info_request")
    brief = brain._brief(dossier.gate(state, {"intent": "free_info_request"}),
                         {"intent": "free_info_request"}, state, [])
    assert "number 3 in a row" in brief
    assert "masterclass" in brief


def test_the_spiral_rule_stays_out_of_a_boundary_conversation():
    """"Is there really nothing that can open them up" is general and tells us nothing new.

    It is also a woman absorbing an answer about her own anatomy, and the masterclass offered at
    that moment is a consolation prize for the thing she has just been told.
    """
    state = None
    for _ in range(3):
        state = _asked(state, "fertility_question")
    state["flags"]["structural"] = "no_uterus"

    gate = dossier.gate(state, {"intent": "fertility_question"})
    assert gate.block_reason == "structural_no_uterus"
    assert "masterclass" not in brain._brief(gate, {"intent": "fertility_question"}, state, [])


# ── The brief on a gated turn ────────────────────────────────────────────────

PARTIAL = {"age": 36, "time_trying": "1 year", "conceiving_mode": "preparing for IVF"}


def test_a_boundary_turn_still_gets_something_to_do():
    """A gate can shut the link. It cannot ask a question, and only the writer can.

    Run two of the m_runs corpus is what the absence of this looks like: four replies that each
    opened by naming something she does not provide, no question in any of them, and a fourth that
    explained the missing link away. The prohibition was the whole brief, so the reply was too.
    """
    read = {"intent": "not_a_fit", "flags": {"wants_unprovided_service": True}}
    gate = dossier.gate(_state(PARTIAL), read)
    brief = brain._brief(gate, read, _state(PARTIAL), [])

    assert "not provide" in brief, "the boundary itself still has to be stated"
    assert "ask the one that would most change what you say next" in brief
    assert "whether having a baby is one of her biggest priorities right now" in brief


@pytest.mark.parametrize("flags,reason", [
    ({"recent_loss": True}, "recent_loss"),
    ({"currently_pregnant": True}, "currently_pregnant"),
    ({"structural": "unclear_tubal"}, "tubal_status_unclear"),
])
def test_the_turns_that_must_not_ask_her_anything_are_not_given_a_question(flags, reason):
    """Grief and a live pregnancy are turns where asking her anything is the mistake, and the
    tubal turn carries a question of its own, which the contract's one question mark is spent on."""
    state = _state(PARTIAL, flags)
    gate = dossier.gate(state, {"intent": "fertility_question"})
    assert gate.block_reason == reason
    assert "ask the one that would most change" not in brain._brief(
        gate, {"intent": "fertility_question"}, state, [],
    )


# ── The narrow safety read ───────────────────────────────────────────────────

async def test_the_safety_read_adds_a_flag_the_extraction_missed():
    """Measured on the recorded run 15 transcript, `asked_if_ai` was missed 4 times in 10.

    Every miss let the writer answer the question itself, and the reply it produced was "I'm the
    person you're talking to here, handling these messages personally".
    """
    client = _FakeClient(
        '{"intent": "warm_prospect", "language": "en", "flags": {}}',
        '{"triggers": ["asked_if_ai"]}',
    )
    read, _ = await reader.read_turn(
        client, [{"role": "user", "content": "hang on, is this a bot?"}], model="gpt-4.1-mini",
    )

    assert read["flags"]["asked_if_ai"] is True
    gate = dossier.gate(dossier.merge(None, read), read)
    assert gate.escalate and gate.escalate_reason == "asked_if_ai"
    assert gate.handover_message == "handover_message_team", "she gets the fixed line, not silence"


async def test_the_safety_read_can_only_add():
    """It sees one message with no conversation around it, which is why it is accurate about that
    message and why it is never allowed to overrule the extraction that saw everything."""
    client = _FakeClient(
        '{"intent": "grief_or_loss", "language": "en", "flags": {"recent_loss": true}}',
        '{"triggers": []}',
    )
    read, _ = await reader.read_turn(
        client, [{"role": "user", "content": "i lost the baby on tuesday"}], model="gpt-4.1-mini",
    )
    assert read["flags"]["recent_loss"] is True


async def test_the_safety_read_only_sees_the_messages_she_just_sent():
    client = _FakeClient('{"intent": "new_prospect", "language": "en"}', '{"triggers": []}')
    await reader.read_turn(client, [
        {"role": "user", "content": "i had a lap last week"},
        {"role": "assistant", "content": "Thank you for telling me that."},
        {"role": "user", "content": "should i stop my letrozole"},
        {"role": "user", "content": "sorry, one more thing"},
    ], model="gpt-4.1-mini")

    asked = client.calls[1]["messages"][-1]["content"]
    assert asked == "should i stop my letrozole\nsorry, one more thing"
    assert "lap last week" not in asked


@pytest.mark.parametrize("junk", ['{"triggers": "crisis"}', "not json at all", '{"triggers": ["nope"]}'])
async def test_a_broken_safety_read_never_invents_a_handover(junk):
    client = _FakeClient('{"intent": "new_prospect", "language": "en"}', junk)
    read, _ = await reader.read_turn(
        client, [{"role": "user", "content": "hi"}], model="gpt-4.1-mini",
    )
    assert not any(read["flags"].get(flag) for flag in reader.SAFETY_FLAGS)


def test_the_masterclass_is_not_offered_twice_in_a_row():
    """The first version of this rule said "every reply after this does the same", and it was
    followed exactly: six consecutive replies of the same two sentences and the same link."""
    state = None
    for _ in range(4):
        state = _asked(state, "free_info_request")
    gate = dossier.gate(state, {"intent": "free_info_request"})

    first = brain._brief(gate, {"intent": "free_info_request"}, state, [])
    assert "send the masterclass link" in first

    state["flags"]["masterclass_sent"] = True
    again = brain._brief(gate, {"intent": "free_info_request"}, state, [])
    assert "do not send it again" in again
    assert "send the masterclass link" not in again


async def test_portuguese_read_as_spanish_is_caught():
    """The confusion runs both ways.

    Measured on the run 12 transcript, the extraction called a Portuguese message `es` 5 times in
    10, and the reply came back in a mixture of the two languages.
    """
    client = _FakeClient('{"intent": "new_prospect", "language": "es"}', NO_TRIGGERS, "other")
    read, _ = await reader.read_turn(
        client, [{"role": "user", "content": "posso escrever em portugues?"}], model="gpt-4.1-mini",
    )

    assert read["language"] == "other"
    gate = dossier.gate(dossier.merge(None, read), read)
    assert gate.escalate and gate.escalate_reason == "language_not_supported"


async def test_the_narrow_call_does_not_pick_between_two_supported_languages():
    """"Sorry i mix languages, is that ok?" is an English sentence in a Spanish conversation.

    The narrow call sees her last few messages and answers `en`, correctly. The extraction saw all
    seven turns and answered `es`. Letting the narrow one win would flip the reply into English and
    drop the Spanish conversations from the prompt, which is not the question it was asked.
    """
    client = _FakeClient('{"intent": "new_prospect", "language": "es"}', NO_TRIGGERS, "en")
    read, _ = await reader.read_turn(
        client, [{"role": "user", "content": "sorry i mix languages, is that ok?"}],
        model="gpt-4.1-mini",
    )
    assert read["language"] == "es"


async def test_english_never_costs_the_extra_call():
    client = _FakeClient('{"intent": "new_prospect", "language": "en"}', NO_TRIGGERS)
    await reader.read_turn(client, [{"role": "user", "content": "hi"}], model="gpt-4.1-mini")
    assert len(client.calls) == 2, "extraction and the safety read, and nothing else"


# ── Two models, two sets of arguments ────────────────────────────────────────

async def test_a_reasoning_reader_is_never_sent_a_temperature():
    """Every call in `reader.py` asked for `temperature=0`, and GPT-5 rejects it with a 400.

    Not a degraded reply, a failed request, on all three calls. The reader failing is a paused
    conversation and a tagged contact, so this is the assertion that stands between a model swap
    in admin and every lead going to a person.
    """
    client = _FakeClient(_OTHER, NO_TRIGGERS, "es")
    await reader.read_turn(
        client, [{"role": "user", "content": "hola, tengo baja reserva"}], model="gpt-5-mini",
    )

    assert len(client.calls) == 3
    for call in client.calls:
        assert "temperature" not in call
        assert call["reasoning_effort"] in ("minimal", "low")
        assert "max_tokens" not in call, "rejected in favour of max_completion_tokens"

    # The extraction is the one worth paying to think about; the two narrow calls judge one short
    # message and stay cheap.
    assert client.calls[0]["reasoning_effort"] == "low"
    assert client.calls[1]["reasoning_effort"] == "minimal"


async def test_a_completion_reader_keeps_its_deterministic_temperature():
    client = _FakeClient(_OTHER, NO_TRIGGERS, "es")
    await reader.read_turn(
        client, [{"role": "user", "content": "hola"}], model="gpt-4.1-mini",
    )
    for call in client.calls:
        assert call["temperature"] == 0
        assert "reasoning_effort" not in call
    assert client.calls[2]["max_tokens"] == 3


async def test_the_language_cap_leaves_a_reasoning_model_room_to_answer():
    """Three tokens is the whole answer, and on a reasoning model it is spent thinking.

    The budget is shared, so a cap sized for `es` returns empty content, and empty content used to
    be read as `other`, which is a silent handover. The headroom is a ceiling, not a spend.
    """
    client = _FakeClient(_OTHER, NO_TRIGGERS, "es")
    await reader.read_turn(client, [{"role": "user", "content": "hola"}], model="gpt-5-mini")
    assert client.calls[2]["max_completion_tokens"] > 3


async def test_an_empty_language_answer_does_not_end_a_spanish_conversation():
    """The failure this guards is silent: she is answered by nobody and never knows why."""
    client = _FakeClient('{"intent": "new_prospect", "language": "es"}', NO_TRIGGERS, "")
    read, _ = await reader.read_turn(
        client, [{"role": "user", "content": "hola, me pueden ayudar?"}], model="gpt-5-mini",
    )

    assert read["language"] == "es", "no opinion is not a verdict of `other`"
    assert not dossier.gate(dossier.merge(None, read), read).escalate


async def test_an_empty_language_answer_leaves_an_unsupported_read_unrescued():
    """The same silence in the other direction must not rescue a lead nobody vouched for."""
    client = _FakeClient(_OTHER, NO_TRIGGERS, "")
    read, _ = await reader.read_turn(
        client, [{"role": "user", "content": "posso escrever em portugues?"}], model="gpt-5-mini",
    )

    assert read["language"] == "other"
    assert read["flags"].get("needs_human")


def test_each_stage_is_costed_at_its_own_rate():
    read_usage = {"prompt_tokens": 10_000, "completion_tokens": 500}
    usage = brain._usage("gpt-5-mini", "gpt-4.1-mini", read_usage, _FakeResponse("hi"))

    expected = (
        brain._cost("gpt-5-mini", 10_000, 500)      # the read, at the reader's rate
        + brain._cost("gpt-4.1-mini", 10, 5)        # the write, at the writer's
    )
    assert usage["token_cost"] == pytest.approx(expected)
    assert usage["token_cost"] != brain._cost("gpt-4.1-mini", 10_010, 505), "one rate for both"
    assert usage["ai_model"] == "gpt-4.1-mini", "the row records who wrote the message"
    assert usage["prompt_tokens"] == 10_010


def test_a_handover_turn_is_costed_on_the_reader_alone():
    usage = brain._usage("gpt-5-mini", "gpt-4.1-mini", {"prompt_tokens": 9_000,
                                                        "completion_tokens": 300}, None)
    assert usage["token_cost"] == pytest.approx(brain._cost("gpt-5-mini", 9_000, 300))
    assert usage["completion_tokens"] == 300


def test_every_model_offered_in_admin_has_a_rate():
    """An unpriced model silently bills at the default's rate, which is how cost reporting lies."""
    for model in (brain.DEFAULT_MODEL, brain.DEFAULT_READ_MODEL):
        assert model in brain._RATES


# ── CTA keywords ─────────────────────────────────────────────────────────────

CTA_CFG = {
    **CFG,
    "cta_keywords": "AMH\nBABY\nBLOOD SUGAR\nREADY",
    "cta_welcome_message": "I'm so glad you reached out. How long have you been trying?",
}


def _said(*texts):
    return [{"role": "user", "content": t} for t in texts]


@pytest.mark.parametrize("text", ["AMH", "amh", "  AMH  ", "AMH!", "amh 🤍", "Blood Sugar",
                                  "blood  sugar", "READY."])
def test_a_keyword_survives_the_way_she_actually_types_it(text):
    """One word commented from a phone arrives with case, punctuation and an emoji on it."""
    assert cta.is_opener(_said(text), CTA_CFG)


@pytest.mark.parametrize("text", [
    "how do I lower my AMH?",           # a question that contains the word
    "AMH came back at 0.7 last month",  # her story, which starts with the word
    "hi",                               # not a keyword at all
    "",
])
def test_only_a_bare_keyword_is_an_opener(text):
    assert not cta.is_opener(_said(text), CTA_CFG)


def test_a_keyword_typed_into_a_conversation_already_under_way_is_a_message():
    """"ready" on turn six is her answering something, and the fixed line would talk over it."""
    history = _said("I'm 38 and been trying 2 years") + [
        {"role": "assistant", "content": "How long has it been?"},
        {"role": "user", "content": "ready"},
    ]
    assert not cta.is_opener(history, CTA_CFG)


def test_a_keyword_followed_by_her_own_message_is_not_an_opener():
    """She commented the word and then typed a sentence before the worker woke up."""
    assert not cta.is_opener(_said("AMH", "I'm 34 and my AMH is 0.7"), CTA_CFG)
    assert cta.is_opener(_said("AMH", "amh"), CTA_CFG), "the same word twice is still the word"


def test_no_keywords_configured_means_nothing_is_an_opener():
    assert not cta.is_opener(_said("AMH"), CFG)


async def test_the_welcome_is_sent_without_calling_a_model():
    """The whole point: one word in, Sonia's own line out, no read call and no write call.

    It also must not qualify her or pause the conversation. A keyword is how the DM opened, so
    "READY" is a reel watched to the end and not a lead asking to book.
    """
    client = _FakeClient("should never be called")
    result = await brain.run_turn(client, _said("AMH"), CTA_CFG)

    assert result.reply_text == CTA_CFG["cta_welcome_message"]
    assert result.action == "CTA_WELCOME"
    assert client.calls == []
    assert result.usage == {}
    assert not result.pause and not result.qualified and not result.add_tag
    assert result.lead_state["phase"] == dossier.OPENING
    assert result.lead_state["counters"].get("turns", 0) == 0, "her answer is the first exchange"


async def test_a_keyword_with_no_welcome_configured_goes_to_the_brain_as_normal():
    """Emptying the message in admin switches the feature off rather than sending nothing."""
    client = _FakeClient('{"intent": "new_prospect", "language": "en"}', NO_TRIGGERS, "Hello.")
    result = await brain.run_turn(client, _said("AMH"), {**CTA_CFG, "cta_welcome_message": ""})

    assert result.action.startswith("REPLY:")
    assert len(client.calls) == 3
