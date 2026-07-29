"""Pure router tests (no LLM, no DB).

The router is where Sonia's central complaint is answered: the qualification
funnel used to be the only path, so pregnancy announcements, thank-you messages
and women who had stopped trying were all qualified.

The most important tests here are NEGATIVE - proving certain conversations can
never reach QUALIFY. Because routing is code, that is provable rather than hoped for.
"""
import pytest

from app.services.brain.classify import Classification, SlotDeltas
from app.services.brain.constants import (
    NEVER_QUALIFY,
    Action,
    LeadIntent,
    ResponseMode,
    Stage,
    empty_lead_state,
)
from app.services.brain.router import derive_stage, route


def cls(intent="answers_question", **overrides):
    """Build a Classification. Slot deltas are passed as plain kwargs."""
    slot_fields = set(SlotDeltas.model_fields)
    slots = {k: overrides.pop(k) for k in list(overrides) if k in slot_fields}
    base = dict(
        language="en",
        intent=intent,
        intent_certainty="certain",
        secondary_intent=None,
        question_asked=None,
        slot_deltas=SlotDeltas(**{k: slots.get(k) for k in slot_fields}),
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


def state(slots=None, flags=None, phase=None):
    st = empty_lead_state()
    st["slots"].update(slots or {})
    st["flags"].update(flags or {})
    if phase:
        st["phase"] = phase
    return st


def qualified_state():
    """A lead who has cleared every gate. Mirrors test_controller.qualified_state."""
    return state(
        slots={"trying_duration": "2 years", "age": 38, "treatment_path": "ivf",
               "what_tried": "IVF", "priority_score": 9, "open_to_holistic": True,
               "financial_ready": True, "partner_status": "solo"},
        flags={"explained_role": True, "situation_shared": True},
    )


# --- THE fix: these conversations are not sales conversations ----------------

@pytest.mark.parametrize("intent,expected_mode", [
    (LeadIntent.PREGNANCY_OR_SUCCESS, ResponseMode.CELEBRATE),
    (LeadIntent.GRATITUDE, ResponseMode.ACKNOWLEDGE),
    (LeadIntent.GRIEF_OR_STOPPED_TRYING, ResponseMode.ACKNOWLEDGE),
    (LeadIntent.EXISTING_CLIENT, ResponseMode.HANDOFF),
    (LeadIntent.COLLABORATION_OR_TECHNICAL, ResponseMode.HANDOFF),
    (LeadIntent.NOT_A_FIT_SIGNAL, ResponseMode.HONEST_DECLINE),
])
def test_never_qualify_intents_get_their_own_mode(intent, expected_mode):
    r = route(state(), cls(intent.value))
    assert r.mode is expected_mode


@pytest.mark.parametrize("intent", sorted(NEVER_QUALIFY, key=lambda i: i.value))
@pytest.mark.parametrize("st", [
    "cold", "mid_funnel", "qualified", "link_sent",
])
def test_never_qualify_intents_never_reach_qualify_at_any_stage(intent, st):
    """The headline guarantee, asserted across every stage a lead can be in.

    Sonia: 'It attempted to qualify pregnancy announcements, gratitude messages
    and emotionally sensitive messages from women who had decided to stop trying.'
    """
    states = {
        "cold": state(),
        "mid_funnel": state(slots={"trying_duration": "2 years", "age": 38},
                            flags={"situation_shared": True}),
        "qualified": qualified_state(),
        "link_sent": {**qualified_state(), "flags": {**qualified_state()["flags"],
                                                     "booking_sent": True}},
    }
    r = route(states[st], cls(intent.value))
    assert r.mode is not ResponseMode.QUALIFY, (
        f"{intent.value} at stage {st} was routed to QUALIFY"
    )
    assert r.mode is not ResponseMode.BOOK, (
        f"{intent.value} at stage {st} was routed to BOOK"
    )


def test_pregnancy_pauses_for_a_human_rather_than_continuing_to_sell():
    r = route(qualified_state(), cls("pregnancy_or_success"))
    assert r.mode is ResponseMode.CELEBRATE
    assert r.pause is True
    assert r.add_tag is True


def test_grief_does_not_get_a_masterclass_redirect():
    """Sonia calls the masterclass redirect out as template matching."""
    r = route(state(), cls("grief_or_stopped_trying"))
    assert r.mode is ResponseMode.ACKNOWLEDGE
    assert r.funnel_action is None
    assert r.pause is True


# --- Complaint 3: answer the question first ----------------------------------

@pytest.mark.parametrize("intent,expected", [
    (LeadIntent.GENERAL_FERTILITY_QUESTION, ResponseMode.ANSWER),
    (LeadIntent.ASKS_FREE_ADVICE, ResponseMode.ANSWER),
    (LeadIntent.ASKS_ABOUT_PROGRAM, ResponseMode.ANSWER),
    (LeadIntent.ASKS_RESULTS_PROOF, ResponseMode.EDUCATE),
    (LeadIntent.ASKS_MASTERCLASS, ResponseMode.RESOURCE),
])
def test_questions_are_answered_not_qualified(intent, expected):
    r = route(state(), cls(intent.value, question_asked="can anything help?"))
    assert r.mode is expected
    assert r.answer_first is True
    assert r.question_asked == "can anything help?"


def test_a_question_mid_funnel_still_gets_answered_first():
    """Sonia: 'the AI avoided answering and moved straight back into
    qualification.' Being mid-funnel is not a reason to deflect."""
    st = state(slots={"trying_duration": "2 years", "age": 38},
               flags={"situation_shared": True})
    r = route(st, cls("general_fertility_question",
                      question_asked="is there anything that helps before IVF?"))
    assert r.mode is ResponseMode.ANSWER
    assert r.answer_first is True


# --- Complaint 6: objections are different conversations ---------------------

@pytest.mark.parametrize("intent,expected", [
    (LeadIntent.OBJECTION_PRICE, ResponseMode.ANSWER),
    (LeadIntent.OBJECTION_PARTNER, ResponseMode.ANSWER),
    (LeadIntent.OBJECTION_PAYING_TWICE, ResponseMode.ANSWER),
    (LeadIntent.OBJECTION_TRUST, ResponseMode.EDUCATE),
    (LeadIntent.OBJECTION_FEAR_AFTER_FAILURE, ResponseMode.ACKNOWLEDGE),
])
def test_objection_subtypes_route_differently(intent, expected):
    r = route(state(), cls(intent.value))
    assert r.mode is expected
    assert r.reason == f"objection:{intent.value}"


def test_objections_do_not_all_collapse_to_one_mode():
    """Sonia: 'The AI often responded to all of them with the same general
    qualification process or redirected them to the free masterclass.'"""
    modes = {route(state(), cls(i.value)).mode
             for i in (LeadIntent.OBJECTION_PRICE, LeadIntent.OBJECTION_TRUST,
                       LeadIntent.OBJECTION_FEAR_AFTER_FAILURE)}
    assert len(modes) > 1


def test_asking_price_marks_financial_engagement_once():
    st = state()
    r = route(st, cls("objection_price"))
    assert r.lead_state["slots"]["financial_ready"] is True
    assert r.lead_state["counters"]["price_ask_count"] == 1


def test_explicit_financial_decline_is_not_overwritten_by_a_price_question():
    st = state(slots={"financial_ready": False})
    r = route(st, cls("objection_price"))
    assert r.lead_state["slots"]["financial_ready"] is False


# --- Complaint 7: not-a-fit and ready-to-book --------------------------------

def test_young_early_lead_is_told_honestly():
    st = state(slots={"age": 29, "trying_duration": "3 months"},
               flags={"situation_shared": True})
    r = route(st, cls("answers_question"))
    assert r.mode is ResponseMode.HONEST_DECLINE
    assert r.reason == "likely_not_a_fit"


def test_high_intent_with_gate_passed_books():
    r = route(qualified_state(), cls("warm_high_intent"))
    assert r.mode is ResponseMode.BOOK
    assert r.qualified is True
    assert r.add_tag is True
    assert r.funnel_action is Action.SEND_BOOKING


def test_high_intent_without_the_gate_still_qualifies():
    """Enthusiasm does not open the gate. This is the Gen 2 failure and it stays shut."""
    r = route(state(), cls("warm_high_intent"))
    assert r.mode is ResponseMode.QUALIFY
    assert r.funnel_action is None


def test_partner_absent_gets_the_couples_booking_message():
    st = qualified_state()
    st["slots"].update({"partner_status": "couple", "partner_can_join": False})
    r = route(st, cls("warm_high_intent"))
    assert r.mode is ResponseMode.BOOK
    assert r.funnel_action is Action.SEND_BOOKING_TOGETHER


# --- Uncertainty routes to a human -------------------------------------------

def test_unsure_intent_goes_to_a_human():
    r = route(state(), cls("other", intent_certainty="unsure"))
    assert r.mode is ResponseMode.HANDOFF
    assert r.pause is True
    assert r.reason == "intent_unclear"


def test_off_script_goes_to_a_human():
    r = route(state(), cls("other", off_script=True))
    assert r.mode is ResponseMode.HANDOFF
    assert r.reason == "off_script"


@pytest.mark.parametrize("intent", ["is_this_ai", "angry_or_challenging", "distress"])
def test_escalation_intents_go_to_a_human_silently(intent):
    r = route(qualified_state(), cls(intent))
    assert r.mode is ResponseMode.HANDOFF
    assert r.send_message is False
    assert r.pause is True


def test_takeover_flag_is_honoured():
    r = route(state(), cls("answers_question", takeover=True, takeover_reason="contradictory"))
    assert r.mode is ResponseMode.HANDOFF
    assert r.pause_reason == "contradictory"


# --- Preserved Gen 3 guarantees ----------------------------------------------

def test_unsupported_language_is_silent():
    r = route(state(), cls("answers_question", language="other"))
    assert r.mode is ResponseMode.HANDOFF
    assert r.send_message is False
    assert r.reason == "unsupported_language"


def test_language_is_sticky_and_unclear_does_not_reset_it():
    st = state(slots={"language": "es"})
    r = route(st, cls("answers_question", language="unclear"))
    assert r.lead_state["slots"]["language"] == "es"


@pytest.mark.parametrize("slots,reason", [
    ({"age": 48}, "age_over_46"),
    ({"tubes_blocked": "both"}, "both_tubes_blocked"),
    ({"no_period_over_year": True}, "no_period_over_12m"),
])
def test_hard_out_of_scope_still_stops_everything(slots, reason):
    r = route(state(slots=slots), cls("answers_question"))
    assert r.mode is ResponseMode.HANDOFF
    assert r.reason == reason
    assert r.pause is True
    assert r.pinned_action is not None, "the approved decline must be pinned verbatim"


def test_out_of_scope_beats_a_pending_question():
    """A 48-year-old asking a question is still out of scope."""
    r = route(state(slots={"age": 48}),
              cls("general_fertility_question", question_asked="can you help me?"))
    assert r.mode is ResponseMode.HANDOFF


def test_ended_conversation_stays_silent():
    st = state(flags={"handed_off": True, "takeover_reason": "qualified_link_sent"})
    r = route(st, cls("answers_question"))
    assert r.mode is ResponseMode.HANDOFF
    assert r.send_message is False
    assert r.add_tag is False, "an ended conversation must not be re-tagged"


def test_cost_declined_then_still_engaging_hands_off():
    st = state(flags={"cost_declined": True})
    r = route(st, cls("answers_question"))
    assert r.mode is ResponseMode.HANDOFF
    assert r.reason == "cant_afford_engaging"


# --- After the link is out ----------------------------------------------------

def test_post_booking_asks_for_the_email_once():
    st = qualified_state()
    st["flags"]["booking_sent"] = True
    r = route(st, cls("booked"))
    assert r.funnel_action is Action.POST_BOOKING_ASK_EMAIL
    assert r.lead_state["phase"] == "POST_BOOKING"


def test_post_booking_email_confirms_then_hands_over():
    st = qualified_state()
    st["flags"]["booking_sent"] = True
    r = route(st, cls("gives_email", email_collected="her@example.com"))
    assert r.funnel_action is Action.POST_BOOKING_ACK
    assert r.pause is True
    assert r.qualified is True
    assert r.lead_state["flags"]["handed_off"] is True


def test_anything_else_after_the_link_goes_to_a_human():
    st = qualified_state()
    st["flags"]["booking_sent"] = True
    r = route(st, cls("objection_price"))
    assert r.mode is ResponseMode.HANDOFF
    assert r.reason == "qualified_link_sent"


def test_link_is_never_sent_twice():
    st = qualified_state()
    st["flags"]["booking_sent"] = True
    r = route(st, cls("warm_high_intent"))
    assert r.mode is not ResponseMode.BOOK


# --- Stage derivation ---------------------------------------------------------

@pytest.mark.parametrize("st,expected", [
    (empty_lead_state(), Stage.COLD),
    (state(flags={"situation_shared": True}), Stage.DISCOVERING),
    (qualified_state(), Stage.QUALIFIED),
])
def test_derive_stage(st, expected):
    assert derive_stage(st) is expected


def test_derive_stage_after_link_and_booking():
    st = qualified_state()
    st["flags"]["booking_sent"] = True
    assert derive_stage(st) is Stage.LINK_SENT
    st["slots"]["email_collected"] = "her@example.com"
    assert derive_stage(st) is Stage.BOOKED


# --- The structural guard -----------------------------------------------------

def test_every_intent_has_a_route():
    """No intent may fall through unhandled at any stage."""
    for intent in LeadIntent:
        for st in (state(), qualified_state()):
            r = route(st, cls(intent.value))
            assert isinstance(r.mode, ResponseMode), f"{intent} produced {r.mode}"


def test_guard_catches_an_unrouted_never_qualify_intent(monkeypatch):
    """If someone adds a never-qualify intent without a branch, it must fail to a
    human rather than silently entering the funnel."""
    import app.services.brain.router as router_mod

    # Pretend ANSWERS_QUESTION is a never-qualify intent with no explicit branch.
    monkeypatch.setattr(router_mod, "NEVER_QUALIFY",
                        frozenset({LeadIntent.ANSWERS_QUESTION}))
    r = route(state(), cls("answers_question"))
    assert r.mode is ResponseMode.HANDOFF
    assert r.reason.startswith("unrouted_never_qualify")
