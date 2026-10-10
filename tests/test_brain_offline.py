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

from app.services import brain, dossier, message_splitter, prompts, reader
from app.services.few_shots import load_few_shot_scenarios, render_examples

FEW_SHOTS = load_few_shot_scenarios("few_shots")

CFG = {
    "booking_link": "https://example.test/free-call",
    "masterclass_link": "https://example.test/register",
    "replay_link": "https://example.test/watch-replay",
    "price_range": "$1,500 to $14,000",
    "years_experience": "16 years",
    "babies_welcomed": "735",
}


# ── The library ──────────────────────────────────────────────────────────────

ALL_BLOCKS = {"pricing", "booking", "free_resource", "post_booking"}


def test_every_playbook_is_a_whole_conversation():
    """Every file is one conversation, first message to outcome, and all of them go out every turn."""
    assert FEW_SHOTS
    for name, pb in FEW_SHOTS.items():
        assert "Lead:" in pb.text and "Sonia:" in pb.text, f"{name} has no dialogue"
        assert pb.text.count("Sonia:") >= 2, f"{name} is a fragment"
        assert not pb.text.startswith("---"), f"{name} still carries its front matter"


def test_endings_are_not_all_booking_links():
    """The old library ended 17 of 18 conversations with the link, which is what taught the
    model to funnel everything toward the calendar."""
    books = sum(1 for pb in FEW_SHOTS.values() if "{{booking_link}}" in pb.text)
    assert books / len(FEW_SHOTS) < 0.55, f"{books} of {len(FEW_SHOTS)} conversations book"


def test_no_file_states_a_link_of_its_own():
    """No literal URL anywhere, placeholders only, resolved from config. Prices are facts and live
    in `knowledge.md` (manual Part 5); links stay in config so the team can change them."""
    offenders = []
    for directory in ("few_shots", "prompts_simple"):
        for filename in sorted(os.listdir(directory)):
            path = os.path.join(directory, filename)
            if not os.path.isfile(path) or filename.startswith("."):
                continue
            text = open(path, encoding="utf-8").read()
            hits = re.findall(r"https?://\S+", text)
            if hits:
                offenders.append((path, hits[:3]))
    assert not offenders, f"literal links found: {offenders}"


def test_first_person_only():
    """Prospect-facing text is always 'I', never 'Sonia' in the third person, except the AI
    disclosure in §F, which is the one place the assistant names her."""
    third_person = re.compile(r"\bSonia's\b|\bSonia (is|was|has|will|can|does|would)\b")
    for name, pb in FEW_SHOTS.items():
        for line in pb.text.splitlines():
            if line.startswith("Sonia:") and "Sonia's AI assistant" not in line:
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
    flags = dict(flags or {})
    state = dossier.merge(None, {"slots": slots or {}, "flags": flags})
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


def test_a_first_message_buyer_gets_the_link_not_the_price():
    """Production, 12 September: "I'm 38, trying 4 years, I want to enrol, can I pay?" §A: the
    enrollment answer or next step immediately, not a financial-readiness warning."""
    read = {
        "intent": "price_question",
        "flags": {"wants_to_buy": True},
        "slots": {"age": 38, "time_trying": "4 years", "conceiving_mode": "natural",
                  "partner_status": "partnered", "goal_stated": "wants to enrol and pay"},
    }
    gate = dossier.gate(dossier.merge(None, read) | {"counters": {"turns": 0}, "phase": None}, read)
    assert gate.allow_booking, gate.block_reason


def test_a_pregnancy_announcement_is_still_terminal():
    """She shared her news and asked for nothing. Nothing is offered into that."""
    read = {"intent": "pregnancy_announcement", "tags": ["celebration"], "slots": {}}
    state = _state(QUALIFIED)
    state["flags"]["currently_pregnant"] = True
    gate = dossier.gate(state, read)
    assert not gate.allow_booking
    assert gate.block_reason == "currently_pregnant"


def test_a_pregnant_woman_who_asks_for_support_can_be_booked():
    """v4 §D, 2B.2 §7: The Pregnancy Solution goes through the same link, with a form note."""
    read = {"intent": "pregnancy_announcement", "slots": {}}
    state = _state({})
    state["flags"].update(currently_pregnant=True, wants_pregnancy_support=True)
    gate = dossier.gate(state, read)
    assert not gate.escalate
    assert gate.allow_booking, gate.block_reason
    assert "booking" in gate.blocks and "attendance" in gate.blocks


def test_a_pregnant_prospect_is_never_age_reviewed():
    """§B: no conception eligibility judgment for an already pregnant TPS prospect."""
    read = {"intent": "warm_prospect", "flags": {"wants_to_buy": True}, "slots": {}}
    state = _state({"age": 50})
    state["flags"].update(currently_pregnant=True, wants_pregnancy_support=True)
    gate = dossier.gate(state, read)
    assert not gate.escalate
    assert gate.allow_booking, gate.block_reason


def test_a_spanish_lead_is_not_booked_before_the_materials_are_disclosed():
    """v2.1 section L: coaching is in Spanish, the materials are in English, and she has to know.

    A deal breaker she finds out about after paying is the failure this gate exists to stop.
    """
    read = {"intent": "program_question", "tags": ["ready_to_book"], "slots": {}}
    state = _state(QUALIFIED)
    state["slots"]["language"] = "es"
    gate = dossier.gate(state, read)
    assert not gate.allow_booking
    assert gate.block_reason == "english_materials_undisclosed"


def test_a_spanish_lead_who_confirms_english_materials_can_be_booked():
    read = {"intent": "program_question", "tags": ["ready_to_book"], "slots": {}}
    state = _state(QUALIFIED)
    state["slots"]["language"] = "es"
    state["flags"]["accepts_english_materials"] = True
    gate = dossier.gate(state, read)
    assert gate.allow_booking, gate.block_reason


def test_an_english_lead_is_never_asked_about_english():
    """The gate keys on the language she is writing in, not on everyone."""
    gate = dossier.gate(_state(QUALIFIED), {"intent": "warm_prospect", "tags": []})
    assert gate.allow_booking


def test_readiness_alone_is_not_an_understanding():
    """The bypass skips the blanket first-turn rule and nothing else.

    "Take my money" with nothing else in it still fails the `known < 3` check in
    `_booking_blocked`, because deciding to buy is not the same as being understood well enough to
    be invited honestly.
    """
    read = {"intent": "price_question", "tags": ["ready_to_book"], "slots": {}}
    gate = dossier.gate(dossier.merge(None, read) | {"counters": {"turns": 0}, "phase": None}, read)
    assert not gate.allow_booking
    assert gate.block_reason == "not_enough_context"


def test_an_unstated_age_no_longer_shuts_the_link():
    """v2.0 §B: age is a boundary check, not a precondition to offering a call.

    It was a precondition, and paired with its place at the head of DISCOVERY that made it the next
    question in every conversation, including the ones that were not qualification conversations at
    all. The cost of removing it is accepted and recorded in `_booking_blocked`: a woman who never
    volunteers a number can reach a consultation the team then screens.
    """
    known_but_ageless = {
        "time_trying": "3 years", "conceiving_mode": "naturally",
        "pregnancy_priority": "high", "partner_status": "husband",
    }
    gate = dossier.gate(_state(known_but_ageless), {"intent": "fertility_question"})
    assert gate.allow_booking
    assert "booking" in gate.blocks


def test_48_and_over_is_reviewed_at_the_link_never_rejected():
    """v4 §B, 2B.1 §10: one age check, at the link, and it is a review."""
    exploring = dossier.gate(_state({**QUALIFIED, "age": 51}), {"intent": "fertility_question"})
    assert not exploring.escalate and not exploring.allow_booking

    ready = dossier.gate(_state({**QUALIFIED, "age": 48}), {"intent": "warm_prospect"})
    assert ready.escalate and ready.escalate_reason == "age_review"
    assert ready.handover_message == "handover_message_review"

    reviewed = _state({**QUALIFIED, "age": 50}, {"age_reviewed": True})
    assert dossier.gate(reviewed, {"intent": "warm_prospect"}).allow_booking

    at_47 = dossier.gate(_state({**QUALIFIED, "age": 47}), {"intent": "warm_prospect"})
    assert at_47.allow_booking and not at_47.escalate


@pytest.mark.parametrize("slots,flags,intent,expected_gate", [
    # Age plus time trying is not yet enough understanding to invite her to a call.
    ({"age": 38, "time_trying": "4 months"}, {}, "fertility_question", "no-link"),
    ({**QUALIFIED, "diagnoses": ["low AMH"]}, {}, "fertility_question", "link"),
    ({"age": 51, "time_trying": "2 years", "pregnancy_priority": "high"}, {},
     "fertility_question", "no-link"),
    (QUALIFIED, {"structural": "unclear_tubal"}, "fertility_question", "no-link"),
    (QUALIFIED, {"requested_lab_interpretation": True}, "advice_request", "no-link"),
    (QUALIFIED, {"wants_unprovided_service": True}, "not_a_fit", "no-link"),
    (QUALIFIED, {"demands_guarantee": True}, "program_question", "no-link"),
    (QUALIFIED, {"recent_loss": True}, "grief_or_loss", "no-link"),
])
def test_the_gate_opens_the_link_only_when_it_should(slots, flags, intent, expected_gate):
    """The flags go to the read as well as to the state, because this is the turn they arrived on and
    one of them, `wants_unprovided_service`, is now read from the turn rather than from the dossier.
    """
    g = dossier.gate(_state(slots, flags), {"intent": intent, "flags": flags})
    assert ("link" if g.allow_booking else "no-link") == expected_gate


# ── The examples in the prompt ───────────────────────────────────────────────

def _examples(blocks):
    return render_examples(list(FEW_SHOTS.values()), allowed_blocks=blocks, values=CFG)


def test_every_conversation_is_shown_on_every_turn():
    """No selection. A turn that may not book still sees the conversations that did."""
    rendered = _examples({"pricing"})
    for name in FEW_SHOTS:
        assert f"### EXAMPLE: {name}" in rendered


@pytest.mark.parametrize("key,block", [
    ("booking_link", "booking"),
    ("masterclass_link", "free_resource"),
    ("replay_link", "post_booking"),
])
def test_a_link_in_an_example_follows_the_gate(key, block):
    """A URL in an example is a URL the writer can copy, so it only appears when its block is open."""
    assert CFG[key] in _examples(ALL_BLOCKS)
    assert CFG[key] not in _examples(ALL_BLOCKS - {block})
    assert "[link not available this turn]" in _examples(ALL_BLOCKS - {block})


def test_examples_resolve_their_placeholders():
    """The writer must never be shown a literal `{{booking_link}}`. It would send it."""
    rendered = _examples(ALL_BLOCKS)
    assert "{{" not in rendered


# ── Prompt assembly ──────────────────────────────────────────────────────────

def test_the_link_is_absent_from_the_prompt_when_the_gate_says_no():
    gated = prompts.build_write_prompt(CFG, {"pricing", "free_resource"})
    assert CFG["booking_link"] not in gated

    allowed = prompts.build_write_prompt(CFG, {"pricing", "free_resource", "booking"})
    assert CFG["booking_link"] in allowed


def test_the_free_link_and_the_booked_link_never_swap_places():
    """Client review point 10: one config key served both stages, so a woman who was never going
    to book was sent the page written for someone who had."""
    free = prompts.build_write_prompt(CFG, {"free_resource"})
    assert CFG["masterclass_link"] in free
    assert CFG["replay_link"] not in free

    booked = prompts.build_write_prompt(CFG, {"post_booking"})
    assert CFG["replay_link"] in booked
    assert CFG["masterclass_link"] not in booked


def test_no_placeholder_survives_into_the_prompt():
    built = prompts.build_write_prompt(CFG, {"pricing", "booking", "free_resource", "post_booking"})
    assert "{{" not in built and "[[BLOCK" not in built


def test_quantities_are_written_as_digits():
    """Client review point 18, enforced rather than asked for.

    The rule is in `60_contract.md` and the few-shots all use digits, and the writer still sent
    "Four years trying naturally at 38". Same licence as `strip_dashes`: typography, not judgment.
    """
    from app.services.message_splitter import use_digits

    assert use_digits("Four years trying naturally at 38.").startswith("4 years")
    assert use_digits("Two weeks of that is a long two weeks.") == "2 weeks of that is a long 2 weeks."
    assert "3 cycles" in use_digits("I would want three cycles of history.")


def test_digits_leave_words_that_are_not_quantities_alone():
    """"one" is a number perhaps a third of the time it appears. The unit is what decides."""
    from app.services.message_splitter import use_digits

    for text in (
        "one of the things I look at",
        "No one has asked you that.",
        "the first thing I would change",
        "Someone will come back to you.",
        "One day it will make sense.",
        "the two-week wait",
        "a second opinion is worth having",
    ):
        assert use_digits(text) == text, text


def test_a_phone_request_does_not_escalate_and_keeps_the_link():
    """Client review point 9, the whole path rather than one definition.

    She asked for a number, which is a channel, not a different person. Nothing hands over, and a
    woman who is otherwise qualified does not lose the link over it.
    """
    read = {"intent": "program_question", "tags": ["phone_request"], "flags": {}, "slots": {}}
    gate = dossier.gate(_state(QUALIFIED), read)
    assert not gate.escalate
    assert gate.allow_booking, gate.block_reason


def test_asking_for_a_person_still_hands_over():
    """The other half. These two look alike and the replies are opposites."""
    read = {"intent": "program_question", "tags": ["human_requested"],
            "flags": {"asked_for_human": True}, "slots": {}}
    gate = dossier.gate(_state(QUALIFIED, flags={"asked_for_human": True}), read)
    assert gate.escalate
    assert gate.escalate_reason == "asked_for_human"


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


@pytest.mark.parametrize("flags,reason", [
    ({"recent_loss": True}, "recent_loss"),
    ({"currently_pregnant": True}, "currently_pregnant"),
    ({"stopped_trying": True}, "stopped_trying"),
    ({"structural": "unclear_tubal"}, "tubal_status_unclear"),
])
def test_the_turns_that_must_not_ask_her_anything_are_not_given_a_question(flags, reason):
    """Grief, a live pregnancy and a woman who has stopped trying are turns where asking her
    anything is the mistake, and the tubal turn carries a question of its own, which the
    contract's one question mark is spent on."""
    state = _state(PARTIAL, flags)
    gate = dossier.gate(state, {"intent": "fertility_question"})
    assert gate.block_reason == reason
    assert "ask the one that would most change" not in brain._brief(
        gate, {"intent": "fertility_question"}, state, [],
    )


# ── A conversation that has ended (v2.0 §A, the terminal path) ───────────────

def test_stopping_shuts_the_link_for_good():
    """Sticky, like every flag. She is not a prospect on the next message either."""
    read = {"intent": "gratitude", "tags": [], "flags": {"stopped_trying": True}}
    state = dossier.merge(_state(PARTIAL), read)
    assert dossier.gate(state, read).block_reason == "stopped_trying"

    later = {"intent": "fertility_question", "tags": [], "flags": {}}
    state = dossier.merge(state, later)
    assert dossier.gate(state, later).block_reason == "stopped_trying"


def test_the_turn_she_says_it_is_offered_nothing_at_all():
    """v2.0 §A: no CTA. The masterclass is a CTA when it answers a decision she has just made."""
    read = {"intent": "gratitude", "tags": [], "flags": {"stopped_trying": True}}
    gate = dossier.gate(dossier.merge(_state(PARTIAL), read), read)
    assert "free_resource" not in gate.blocks and "booking" not in gate.blocks

    built = prompts.build_write_prompt(CFG, gate.blocks)
    assert CFG["masterclass_link"] not in built and CFG["booking_link"] not in built


def test_a_question_asked_afterwards_is_still_answered_properly():
    """Terminal describes the message, not the rest of her life. The link stays shut; the free
    resource comes back, because withholding it from a woman who asked would be its own failure."""
    said = {"intent": "gratitude", "tags": [], "flags": {"stopped_trying": True}}
    state = dossier.merge(_state(PARTIAL), said)

    later = {"intent": "fertility_question", "tags": [], "flags": {}}
    gate = dossier.gate(dossier.merge(state, later), later)
    assert "free_resource" in gate.blocks
    assert not gate.allow_booking


def test_a_fresh_loss_outranks_the_decision_she_made_about_it():
    """"We lost it at 11 weeks and we've decided that's it" sets both. The loss is what the reply
    has to stay with, and the terminal turn gives up nothing by losing: neither may ask, offer or
    send a link, and the free resource is withheld on the flag rather than on the reason."""
    read = {"intent": "grief_or_loss", "tags": [],
            "flags": {"recent_loss": True, "stopped_trying": True}}
    gate = dossier.gate(dossier.merge(_state(PARTIAL), read), read)
    assert gate.block_reason == "recent_loss"
    assert "free_resource" not in gate.blocks and not gate.allow_booking


# ── The narrow safety read ───────────────────────────────────────────────────

async def test_the_safety_read_adds_a_flag_the_extraction_missed():
    """Measured on the recorded run 15 transcript, `asked_if_ai` was missed 4 times in 10.

    Every miss let the writer deny it, and the reply it produced was "I'm the person you're talking
    to here, handling these messages personally". The flag is still caught as generously as it ever
    was; what changed in v2.0 §F is what happens next.
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
    assert not gate.escalate, "she asked a question, she did not ask for a person"


def test_saying_yes_to_a_person_is_what_hands_over():
    read = {"intent": "fertility_question", "tags": [], "flags": {"asked_for_human": True}}
    gate = dossier.gate(dossier.merge(None, read), read)
    assert gate.escalate and gate.escalate_reason == "asked_for_human"


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


# ── The six conversations of the 12 September sandbox run ────────────────────
#
# Codex drove the admin sandbox through the six conversations in `codex-test-prompt.md` and three
# of them failed. Each test below pins the mechanism behind one failure, so the next change to a
# prompt layer or a conversation file cannot quietly restore it.


async def test_asking_for_a_person_in_the_same_breath_still_hands_over():
    """The other half of it. She wants a number and she wants somebody else, so both are true."""
    client = _FakeClient(
        '{"intent": "new_prospect", "tags": ["phone_request", "human_requested"], '
        '"language": "en", "flags": {"asked_for_human": true}}',
        NO_TRIGGERS,
    )
    read, _ = await reader.read_turn(
        client, [{"role": "user", "content": "number for someone on your team i can ring"}],
        model="gpt-4.1-mini",
    )

    assert read["flags"]["asked_for_human"]


def test_no_paid_warning_stands_between_her_and_the_link():
    """2B.1 §11 and 2B.2 §7: price is answered when asked, never required before booking."""
    read = {"intent": "program_question"}
    gate = dossier.gate(_state(QUALIFIED), read)

    assert gate.allow_booking


def test_a_fresh_loss_is_offered_no_free_resource():
    """The link was already shut. The masterclass was still being rendered into the prompt."""
    read = {"intent": "grief_or_loss"}
    gate = dossier.gate(_state(QUALIFIED, flags={"recent_loss": True}), read)

    assert not gate.allow_booking
    assert "free_resource" not in gate.blocks


def test_the_pregnancy_program_is_named_when_she_asks_for_it():
    """And the turn says so, because "yes, I do support women through pregnancy" leaves her having
    to ask a second time what the thing is."""
    read = {"intent": "pregnancy_announcement", "tags": ["celebration", "pregnancy_support"],
            "flags": {"currently_pregnant": True, "wants_pregnancy_support": True},
            "slots": {"miscarriage_history": "3 losses"}}
    state = dossier.merge(None, read)
    brief = brain._brief(dossier.gate(state, read), read, state, [])

    assert "The Pregnancy Solution" in brief




# ── v4.0: handover, after the link, attendance, proof ───────────────────────

@pytest.mark.parametrize("reason,message", [
    ("asked_for_human", "handover_message_review"),
    ("requested_medication", "handover_message_review"),
    ("complaint", "handover_message_review"),
    ("crisis", "handover_message_crisis"),
    ("urgent_medical", "handover_message_urgent_medical"),
    ("abusive", ""),
    ("spam_or_aggression", ""),
])
def test_every_review_sends_the_acknowledgment_except_safety_and_abuse(reason, message):
    """v4 §F, 2B.2 §13: the acknowledgment is the default, once, on every review."""
    assert dossier.handover_message(reason) == message


def _after_link(slots=None, phase=dossier.LINK_SENT):
    state = _state({**QUALIFIED, **(slots or {})}, phase=phase)
    return state


def test_after_the_link_thanks_gets_nothing():
    before = _after_link()
    read = {"intent": "gratitude", "flags": {}, "slots": {}}
    gate = dossier.gate(dossier.merge(before, read), read, before)
    assert gate.silent and not gate.escalate


def test_after_the_link_saying_she_booked_gets_a_reply():
    before = _after_link()
    read = {"intent": "new_prospect", "flags": {"says_booked": True}, "slots": {}}
    state = dossier.merge(before, read)
    gate = dossier.gate(state, read, before)
    assert not gate.silent and "post_booking" not in gate.blocks
    assert "Ask for the email" in brain._brief(gate, read, state, [])


def test_after_the_link_her_email_opens_the_preparation_video():
    before = _after_link()
    read = {"intent": "new_prospect", "flags": {}, "slots": {"email": "jo@mail.com"}}
    state = dossier.merge(before, read)
    gate = dossier.gate(state, read, before)
    assert "post_booking" in gate.blocks
    assert "preparation message" in brain._brief(gate, read, state, [])


def test_the_preparation_lines_go_once():
    before = _after_link({"email": "jo@mail.com"}, phase=dossier.POST_BOOKING)
    read = {"intent": "new_prospect", "flags": {"says_booked": True}, "slots": {}}
    assert dossier.gate(dossier.merge(before, read), read, before).silent


def test_a_crisis_after_the_link_still_hands_over():
    before = _after_link()
    read = {"intent": "new_prospect", "flags": {"crisis": True}, "slots": {}}
    gate = dossier.gate(dossier.merge(before, read), read, before)
    assert gate.escalate and gate.handover_message == "handover_message_crisis"


def test_attendance_pushback_gets_one_question_then_never_again():
    """2B.1 §12: one question on pushback; once answered, it can't repeat."""
    before = _after_link()
    push = {"slots": {"attendance": "pushback"}, "flags": {}}
    state = dossier.merge(before, push)
    assert brain._attendance_note(state, before) == "attendance_pushback"

    answered = dossier.merge(state, {"slots": {"attendance": "together"}, "flags": {}})
    again_before = answered
    again = dossier.merge(answered, push)
    assert brain._attendance_note(again, again_before) == "attendance_together"


def test_an_agreed_exception_is_given_and_remembered_after_booking():
    before = _after_link({"attendance": "partner_cannot_attend", "partner_status": "partnered"})
    read = {"intent": "new_prospect", "flags": {"says_booked": True}, "slots": {"email": "a@b.co"}}
    state = dossier.merge(before, read)
    gate = dossier.gate(state, read, before)
    brief = brain._brief(gate, read, state, [], "")
    assert "agreed she would come on her own" in brief


def test_donor_sperm_is_not_a_relationship_status():
    state = _state({**QUALIFIED, "partner_status": "same_sex_partner", "donor_sperm": True})
    gate = dossier.gate(state, {"intent": "warm_prospect"})
    brief = brain._brief(gate, {"intent": "warm_prospect"}, state, [])
    assert "attendance line" in brief


def test_a_solo_mother_is_invited_alone():
    state = _state({**QUALIFIED, "partner_status": "single_by_choice", "donor_sperm": True})
    gate = dossier.gate(state, {"intent": "warm_prospect"})
    assert "invite her alone" in brain._brief(gate, {"intent": "warm_prospect"}, state, [])


def test_client_stories_open_only_when_she_asks():
    asked = {"intent": "program_question", "flags": {"asked_about_results": True}}
    assert "proof" in dossier.gate(_state(QUALIFIED), asked).blocks
    assert "proof" not in dossier.gate(_state(QUALIFIED), {"intent": "program_question"}).blocks


def test_ok_after_booked_is_not_asked_for_the_email_again():
    """The reader reads booking from the whole conversation, so the flag comes back on "ok"."""
    before = _after_link()
    booked = {"intent": "new_prospect", "flags": {"says_booked": True}, "slots": {}}
    state = dossier.merge(before, booked)
    assert dossier.gate(state, booked, before).after_link == "booked"
    ok = {"intent": "new_prospect", "flags": {"says_booked": True}, "slots": {}}
    assert dossier.gate(dossier.merge(state, ok), ok, state).silent


def test_a_question_before_booking_is_answered_after_the_link():
    """Part 1 §3: her question is never ignored, even once she has the link."""
    before = _after_link()
    read = {"intent": "program_question", "explicit_question": "which level should i do?",
            "flags": {}, "slots": {}}
    gate = dossier.gate(dossier.merge(before, read), read, before)
    assert gate.after_link == "question" and "booking" not in gate.blocks
