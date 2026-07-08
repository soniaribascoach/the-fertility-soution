"""Exhaustive unit tests for the flow controller (Step 4). Pure, no LLM, no DB.

This is the heart of the anti-hallucination design: every guarantee Sonia asked
for (never book early, never repeat a question, OOS -> takeover) is enforced
here as code, so it is tested here deterministically.
"""
from app.services.brain.constants import Action, Phase, empty_lead_state
from app.services.brain.controller import decide, booking_gate
from app.services.brain.extractor import Extraction, SlotDeltas
from app.services.brain import scripts


def ext(intent="other", situation_type="none", oos_signal="none",
        takeover=False, takeover_reason=None, confidence=0.9, language="en", **slots):
    deltas = SlotDeltas(**{k: slots.get(k) for k in SlotDeltas.model_fields})
    return Extraction(
        slot_deltas=deltas, intent=intent, situation_type=situation_type,
        oos_signal=oos_signal, language=language, takeover=takeover,
        takeover_reason=takeover_reason, confidence=confidence,
    )


def state(slots=None, flags=None, counters=None, phase=None):
    st = empty_lead_state()
    if phase:
        st["phase"] = phase
    st["slots"].update(slots or {})
    st["flags"].update(flags or {})
    st["counters"].update(counters or {})
    return st


def qualified_state():
    """A lead that satisfies every booking-gate criterion (link not yet sent)."""
    return state(
        slots={
            "trying_duration": "2 years", "age": 38, "treatment_path": "ivf",
            "what_tried": "IVF", "priority_score": 9, "open_to_holistic": True,
            "financial_ready": True, "partner_status": "solo",
        },
        flags={"explained_role": True, "situation_shared": True},
    )


# --- Discovery: ask the next MISSING question, never a known one -------------

def test_discovery_asks_next_missing_question():
    d = decide(empty_lead_state(), ext(intent="shares_situation", trying_duration="2 years"))
    assert d.action == Action.ASK_DISCOVERY
    assert d.composer_brief["next_question"] == scripts.DISCOVERY_QUESTIONS["age"]
    assert d.lead_state["flags"]["situation_shared"] is True


def test_discovery_never_repeats_answered_questions():
    # duration + what_tried already known; the new message gives age.
    st = state(slots={"trying_duration": "2 years", "what_tried": "2 IUIs"})
    d = decide(st, ext(intent="shares_situation", age=41))
    # Discovery is now complete -> advance to priority, do NOT re-ask anything.
    assert d.action == Action.ASK_PRIORITY
    assert d.lead_state["phase"] == Phase.PRIORITY.value


def test_discovery_reflects_known_facts_to_composer():
    st = state(slots={"trying_duration": "2 years", "age": 41})
    d = decide(st, ext(intent="shares_situation", what_tried="2 IUIs"))
    # age not yet -> wait, age is set; treatment/what_tried now set -> complete.
    # Use a case that stays in discovery: only duration known, learns nothing new path:
    st2 = state(slots={"trying_duration": "2 years"})
    d2 = decide(st2, ext(intent="shares_situation", diagnosis_detail="PCOS"))
    assert d2.action == Action.ASK_DISCOVERY
    assert "trying_duration" in d2.composer_brief["facts_to_reflect"]


def test_empathy_variant_passed_for_misfortune():
    d = decide(empty_lead_state(),
               ext(intent="shares_situation", situation_type="misfortune", what_tried="failed IVF"))
    assert d.composer_brief["empathy_line"] == scripts.EMPATHY_VARIANTS["misfortune"]


# --- The booking gate: the single most important guarantee ------------------

def test_fully_qualified_lead_gets_booking_link():
    d = decide(qualified_state(), ext(intent="ready_to_book"))
    assert d.action == Action.SEND_BOOKING
    assert d.lead_state["phase"] == Phase.POST_BOOKING.value
    assert d.lead_state["flags"]["booking_sent"] is True


def test_booking_blocked_when_any_single_criterion_missing():
    # Flip off each gate criterion in turn; SEND_BOOKING must be unreachable.
    mutations = [
        {"slots": {"priority_score": 5}},        # priority < 8
        {"slots": {"open_to_holistic": None}},   # role not accepted
        {"slots": {"financial_ready": None}},    # financial not confirmed
        {"slots": {"financial_ready": False}},   # financial declined
        {"slots": {"partner_status": "couple", "partner_can_join": None}},  # partner unresolved
        {"flags": {"explained_role": False, "situation_shared": True}},     # role never explained
    ]
    for mut in mutations:
        st = qualified_state()
        st["slots"].update(mut.get("slots", {}))
        st["flags"].update(mut.get("flags", {}))
        d = decide(st, ext(intent="ready_to_book"))
        assert d.action != Action.SEND_BOOKING, f"booked despite {mut}"


def test_ready_to_book_does_not_short_circuit_qualification():
    # Lead insists on booking but has shared almost nothing -> keep qualifying.
    d = decide(empty_lead_state(), ext(intent="ready_to_book", trying_duration="6 months"))
    assert d.action == Action.ASK_DISCOVERY


def test_booking_gate_predicate_matches_decision():
    assert booking_gate(qualified_state()) is True
    st = qualified_state()
    st["slots"]["financial_ready"] = None
    assert booking_gate(st) is False


# --- Priority ----------------------------------------------------------------

def test_priority_asked_after_discovery():
    st = state(slots={"trying_duration": "2 years", "age": 38, "treatment_path": "natural"})
    d = decide(st, ext(intent="answers_question"))
    assert d.action == Action.ASK_PRIORITY
    assert d.lead_state["flags"]["asked_priority"] is True


def test_emotional_nonanswer_reasks_priority_not_reengage():
    # "It's been hard and discouraging" (no number) must NOT trigger the sales
    # re-engagement script; gently re-ask instead (the test_3 miss).
    slots = {"trying_duration": "2y", "age": 38, "treatment_path": "natural"}
    st = state(slots=slots, flags={"asked_priority": True})
    d = decide(st, ext(intent="answers_question", situation_type="hopeless"))
    assert d.action == Action.ASK_PRIORITY
    assert d.action not in (Action.REENGAGE_LOW_PRIORITY, Action.LOW_PRIORITY_INFO_GATHERING)


def test_low_priority_reengages_then_offers_info_gathering():
    base = state(
        slots={"trying_duration": "2 years", "age": 38, "treatment_path": "natural",
               "priority_score": 5},
        flags={"asked_priority": True},
    )
    d1 = decide(base, ext(intent="answers_question"))
    assert d1.action == Action.REENGAGE_LOW_PRIORITY
    assert d1.lead_state["counters"]["priority_reengage_count"] == 1
    # Still low after re-engagement.
    base2 = state(
        slots={"trying_duration": "2 years", "age": 38, "treatment_path": "natural",
               "priority_score": 5},
        flags={"asked_priority": True},
        counters={"priority_reengage_count": 1},
    )
    d2 = decide(base2, ext(intent="answers_question"))
    assert d2.action == Action.LOW_PRIORITY_INFO_GATHERING


# --- Explain role ------------------------------------------------------------

def test_explain_role_then_confirm_then_advance():
    pri_done = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf", "priority_score": 9}
    d1 = decide(state(slots=pri_done), ext(intent="answers_question"))
    assert d1.action == Action.EXPLAIN_ROLE
    assert d1.lead_state["flags"]["explained_role"] is True

    d2 = decide(state(slots=pri_done, flags={"explained_role": True}),
                ext(intent="answers_question"))
    assert d2.action == Action.EXPLAIN_ROLE_CONFIRM

    d3 = decide(state(slots={**pri_done, "open_to_holistic": True}, flags={"explained_role": True}),
                ext(intent="answers_question"))
    assert d3.action == Action.FINANCIAL_CHECK


# --- Financial ---------------------------------------------------------------

def test_persistent_low_priority_ends_with_nurture_close():
    # The test_2 loop: a not-ready lead must be closed out, not asked forever.
    slots = {"trying_duration": "1y", "age": 34, "treatment_path": "natural", "priority_score": 4}
    st = state(slots=slots, flags={"asked_priority": True})
    d1 = decide(st, ext(intent="answers_question"))
    assert d1.action == Action.REENGAGE_LOW_PRIORITY
    d2 = decide(d1.lead_state, ext(intent="answers_question"))
    assert d2.action == Action.LOW_PRIORITY_INFO_GATHERING
    d3 = decide(d2.lead_state, ext(intent="answers_question"))
    assert d3.action == Action.NURTURE_CLOSE
    assert d3.pause is True and d3.add_tag is True
    assert d3.lead_state["flags"]["handed_off"] is True
    # After the soft close the AI stays silent.
    d4 = decide(d3.lead_state, ext(intent="other"))
    assert d4.action == Action.HUMAN_TAKEOVER and d4.send_message is False


def test_explain_role_fires_even_if_already_open_to_holistic():
    # She pre-stated she wants holistic (open_to_holistic True) but must still hear
    # the not-a-doctor role once. The only escape hatch is understands_role=True
    # (she stated in her own words she knows this is coaching, not medical care).
    slots = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf",
             "priority_score": 9, "open_to_holistic": True}
    d = decide(state(slots=slots), ext(intent="answers_question"))
    assert d.action == Action.EXPLAIN_ROLE


def test_understands_role_skips_explain_role():
    # Sonia v1.1: her own "I understand this is coaching, not medical care"
    # satisfies the role step -> advance to financial, no EXPLAIN_ROLE re-run.
    slots = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf",
             "priority_score": 9, "understands_role": True}
    d = decide(state(slots=slots), ext(intent="answers_question"))
    assert d.action == Action.FINANCIAL_CHECK


def test_understands_role_alone_does_not_book():
    d = decide(empty_lead_state(), ext(intent="answers_question", understands_role=True))
    assert d.action == Action.ASK_DISCOVERY


def test_open_to_holistic_false_blocks_despite_understands_role():
    slots = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf",
             "priority_score": 9, "understands_role": True, "open_to_holistic": False,
             "financial_ready": True, "partner_status": "solo"}
    d = decide(state(slots=slots, flags={"explained_role": True, "situation_shared": True}),
               ext(intent="answers_question"))
    assert d.action == Action.SOCIAL_PROOF
    assert d.action != Action.SEND_BOOKING


def test_partner_mention_infers_couple_status():
    # "my husband can join" sets partner_can_join without partner_status;
    # merge() must infer couple so the partner gate can resolve.
    d = decide(empty_lead_state(), ext(intent="answers_question", partner_can_join=True))
    assert d.lead_state["slots"]["partner_status"] == "couple"


def test_one_message_fully_qualified_lead_books():
    # Sonia's headline v1.1 bug: every criterion stated in ONE message must
    # send the booking link that same turn.
    d = decide(empty_lead_state(), ext(
        intent="shares_situation", age=38, trying_duration="18 months",
        done_testing=True, treatment_path="natural", priority_score=10,
        understands_role=True, financial_ready=True, partner_can_join=True,
    ))
    assert d.action == Action.SEND_BOOKING
    assert d.qualified is True


def test_financial_decline_blocks_booking():
    slots = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf",
             "priority_score": 9, "open_to_holistic": True, "financial_ready": False}
    d = decide(state(slots=slots, flags={"explained_role": True}), ext(intent="not_ready_no_money"))
    # not_ready_no_money interrupt -> NO_MONEY (also acceptable: FINANCIAL_DECLINE), never booking.
    assert d.action in (Action.NO_MONEY, Action.FINANCIAL_DECLINE)
    assert d.action != Action.SEND_BOOKING


# --- Partner -----------------------------------------------------------------

def test_partner_join_then_pushback_then_resolved():
    base = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf", "priority_score": 9,
            "open_to_holistic": True, "financial_ready": True}
    flags = {"explained_role": True}

    d_ask = decide(state(slots={**base, "partner_status": "couple"}, flags=flags),
                   ext(intent="answers_question"))
    assert d_ask.action == Action.PARTNER_ASK_JOIN

    d_push = decide(
        state(slots={**base, "partner_status": "couple", "partner_can_join": False,
                     "partner_is_decision_maker": True}, flags=flags),
        ext(intent="answers_question"))
    assert d_push.action == Action.PARTNER_PUSHBACK

    d_ok = decide(
        state(slots={**base, "partner_status": "couple", "partner_can_join": True}, flags=flags),
        ext(intent="answers_question"))
    assert d_ok.action == Action.SEND_BOOKING


def test_partner_refusal_never_books_without_decision_maker_answer():
    # Sonia v1.1: "my husband doesn't want to join" sent the booking link.
    # Even if the extractor over-infers sole-decision-maker on the refusal
    # turn, merge() drops that delta and the bot asks the question first.
    base = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf", "priority_score": 9,
            "open_to_holistic": True, "financial_ready": True}
    st = state(slots=base, flags={"explained_role": True, "situation_shared": True})
    d = decide(st, ext(intent="answers_question", partner_status="couple",
                       partner_can_join=False, partner_is_decision_maker=False))
    assert d.action == Action.PARTNER_PUSHBACK
    assert d.lead_state["slots"]["partner_is_decision_maker"] is None

    # Her explicit follow-up answer resolves it -> booking.
    d2 = decide(d.lead_state, ext(intent="answers_question", partner_is_decision_maker=False))
    assert d2.action == Action.SEND_BOOKING


def test_partner_pushback_loop_guard_hands_off():
    base = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf", "priority_score": 9,
            "open_to_holistic": True, "financial_ready": True,
            "partner_status": "couple", "partner_can_join": False}
    st = state(slots=base, flags={"explained_role": True, "situation_shared": True})
    d1 = decide(st, ext(intent="answers_question"))
    assert d1.action == Action.PARTNER_PUSHBACK
    d2 = decide(d1.lead_state, ext(intent="answers_question"))
    assert d2.action == Action.PARTNER_PUSHBACK
    d3 = decide(d2.lead_state, ext(intent="answers_question"))
    assert d3.action == Action.HUMAN_TAKEOVER


def test_solo_lead_skips_partner_and_books():
    base = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf", "priority_score": 9,
            "open_to_holistic": True, "financial_ready": True, "partner_status": "single_by_choice"}
    d = decide(state(slots=base, flags={"explained_role": True}), ext(intent="answers_question"))
    assert d.action == Action.SEND_BOOKING


# --- Post-booking ------------------------------------------------------------

def test_booking_link_is_terminal_qualified_handoff():
    # Sending the link is the AI's last act: it pauses + tags qualified and hands
    # off (the AI can't verify the email). No email/confirmation dance, no re-sends.
    d = decide(qualified_state(), ext(intent="ready_to_book"))
    assert d.action == Action.SEND_BOOKING
    assert d.pause is True and d.qualified is True and d.add_tag is True
    assert d.lead_state["flags"]["handed_off"] is True


def test_after_handoff_stays_silent():
    booked = qualified_state()
    booked["flags"]["booking_sent"] = True
    booked["flags"]["handed_off"] = True
    d = decide(booked, ext(intent="other"))
    assert d.action == Action.HUMAN_TAKEOVER
    assert d.send_message is False and d.pause is True


# --- Out of scope + takeover -------------------------------------------------

def test_blocked_tubes_clarify_then_oos():
    d_ask = decide(empty_lead_state(), ext(oos_signal="blocked_tubes"))
    assert d_ask.action == Action.ASK_BOTH_TUBES
    assert d_ask.pause is False

    # "my tubes are blocked" without a count -> still clarify, never assume both.
    d_unspec = decide(empty_lead_state(),
                      ext(oos_signal="blocked_tubes", tubes_blocked="unspecified"))
    assert d_unspec.action == Action.ASK_BOTH_TUBES
    assert d_unspec.pause is False

    d_oos = decide(empty_lead_state(), ext(oos_signal="blocked_tubes", tubes_blocked="both"))
    assert d_oos.action == Action.OOS_BOTH_TUBES
    assert d_oos.pause is True and d_oos.add_tag is True
    assert d_oos.lead_state["phase"] == Phase.OOS.value


def test_one_blocked_tube_acknowledged_then_continues():
    # Sonia v1.1: one tube -> acknowledge the one-vs-both difference + stage
    # question (never the generic first question), and no takeover.
    d = decide(empty_lead_state(), ext(oos_signal="blocked_tubes", tubes_blocked="one"))
    assert d.action == Action.ONE_TUBE_ACK
    assert d.pause is False

    # Stage already known -> no ack detour, the funnel just continues.
    st = state(slots={"what_tried": "2 IUIs"})
    d2 = decide(st, ext(oos_signal="blocked_tubes", tubes_blocked="one"))
    assert d2.action == Action.ASK_DISCOVERY

    # Ack fires only on the delta turn -> next turn continues the funnel.
    d3 = decide(d.lead_state, ext(intent="answers_question", treatment_path="iui"))
    assert d3.action == Action.ASK_DISCOVERY


def test_age_over_46_pauses():
    d = decide(empty_lead_state(), ext(oos_signal="age_over_46", age=48))
    assert d.action == Action.OOS_AGE_OVER_46
    assert d.pause is True and d.add_tag is True


def test_age_over_46_is_deterministic_without_llm_flag():
    # The test_2 bug: extractor got age=48 but did NOT flag oos_signal. Code must
    # still trigger the takeover from the number alone.
    d = decide(empty_lead_state(), ext(intent="answers_question", age=48))
    assert d.action == Action.OOS_AGE_OVER_46
    assert d.pause is True and d.add_tag is True


def test_both_tubes_deterministic_without_llm_flag():
    d = decide(empty_lead_state(), ext(intent="answers_question", tubes_blocked="both"))
    assert d.action == Action.OOS_BOTH_TUBES
    assert d.pause is True and d.add_tag is True


def test_age_46_exactly_is_not_oos():
    # Spec cutoff is "over 46", so 46 continues.
    d = decide(empty_lead_state(), ext(intent="shares_situation", age=46, trying_duration="1 year"))
    assert d.action != Action.OOS_AGE_OVER_46


def test_menopause_multistep():
    # Age unknown -> ask her age (needed to decide).
    d_age = decide(empty_lead_state(), ext(oos_signal="menopause_no_period"))
    assert d_age.action == Action.ASK_MENOPAUSE_AGE

    # 40+ with a menopause / long no-period signal -> out of scope.
    d_oos = decide(empty_lead_state(), ext(oos_signal="menopause_no_period", age=44))
    assert d_oos.action == Action.OOS_MENOPAUSE and d_oos.pause is True

    # Younger than 40, no reason yet -> ask the reason.
    d_reason = decide(empty_lead_state(), ext(oos_signal="menopause_no_period", age=33))
    assert d_reason.action == Action.ASK_MENOPAUSE_REASON

    # Younger than 40 with a benign reason -> continue the funnel.
    d_young = decide(empty_lead_state(),
                     ext(oos_signal="menopause_no_period", age=33, no_period_reason="stress"))
    assert d_young.action == Action.ASK_DISCOVERY


def test_is_this_ai_triggers_takeover():
    d = decide(empty_lead_state(), ext(intent="is_this_ai", takeover=True, takeover_reason="asked if AI"))
    assert d.action == Action.HUMAN_TAKEOVER
    assert d.send_message is False
    assert d.pause is True and d.add_tag is True


# --- Language ----------------------------------------------------------------

def test_unsupported_language_is_silent():
    # Not en/es -> say NOTHING (she can't read our decline); pause + tag a human.
    d = decide(empty_lead_state(), ext(language="other"))
    assert d.action == Action.UNSUPPORTED_LANGUAGE
    assert d.send_message is False
    assert d.pause is True and d.add_tag is True
    assert d.pause_reason == "unsupported_language"


def test_language_sticky_updates_on_confident_turn():
    st = state(slots={"language": "en", "trying_duration": "1 year"})
    d = decide(st, ext(language="es", intent="shares_situation", age=34))
    assert d.lead_state["slots"]["language"] == "es"
    assert d.action != Action.UNSUPPORTED_LANGUAGE  # the funnel continues


def test_unclear_keeps_prior_language():
    st = state(slots={"language": "es", "trying_duration": "1 year"})
    d = decide(st, ext(language="unclear", intent="answers_question"))
    assert d.lead_state["slots"]["language"] == "es"


def test_other_language_beats_oos_decline():
    # A French-speaking 48-year-old must get silence, not the English age decline.
    d = decide(empty_lead_state(), ext(language="other", age=48))
    assert d.action == Action.UNSUPPORTED_LANGUAGE
    assert d.send_message is False


def test_other_does_not_overwrite_sticky_slot():
    st = state(slots={"language": "es"})
    d = decide(st, ext(language="other"))
    assert d.action == Action.UNSUPPORTED_LANGUAGE
    assert d.lead_state["slots"]["language"] == "es"


# --- Interrupts (answer, then resume) ---------------------------------------

def test_price_deflect_then_range_escalation():
    # 1st ask (discovery complete) -> late deflect, no number, no link.
    d1 = decide(qualified_state(), ext(intent="asks_price"))
    assert d1.action == Action.PRICE_DEFLECT_LATE
    assert d1.lead_state["counters"]["price_ask_count"] == 1
    assert d1.action != Action.SEND_BOOKING

    # 2nd ask -> reveal the range.
    st2 = qualified_state()
    st2["counters"]["price_ask_count"] = 1
    d2 = decide(st2, ext(intent="asks_price"))
    assert d2.action == Action.PRICE_RANGE

    # 3rd ask -> firm restate, push to call.
    st3 = qualified_state()
    st3["counters"]["price_ask_count"] = 2
    d3 = decide(st3, ext(intent="asks_price"))
    assert d3.action == Action.PRICE_RANGE_FIRM


def test_price_deflect_never_reasks_known_facts():
    # The reported bug: deflection must not re-ask facts already shared.
    st = qualified_state()  # discovery already complete
    d = decide(st, ext(intent="asks_price"))
    assert "how long have you been trying" not in scripts.render(d.action).lower()


def test_early_price_ask_still_redirects_to_discovery():
    # When discovery is genuinely incomplete, the deflect SHOULD ask for it.
    d = decide(empty_lead_state(), ext(intent="asks_price"))
    assert d.action == Action.PRICE_DEFLECT


def test_cant_afford_then_keeps_engaging_hands_off():
    # First cost decline -> soft NO_MONEY; any further engagement -> human takeover
    # (the spec's "cannot afford but keeps engaging" trigger).
    d1 = decide(empty_lead_state(), ext(intent="not_ready_no_money"))
    assert d1.action == Action.NO_MONEY
    assert d1.lead_state["flags"]["cost_declined"] is True
    d2 = decide(d1.lead_state, ext(intent="asks_advice"))
    assert d2.action == Action.HUMAN_TAKEOVER
    assert d2.pause is True and d2.add_tag is True


def test_advice_escalation_stage_aware():
    # Discovery incomplete -> deflect variants that ask for discovery.
    d1 = decide(empty_lead_state(), ext(intent="asks_advice"))
    assert d1.action == Action.ADVICE_DEFLECT
    d2 = decide(state(counters={"advice_push_count": 1}), ext(intent="asks_advice"))
    assert d2.action == Action.ADVICE_DEFLECT_PUSH
    # Discovery complete -> 'late' variants that do NOT re-ask.
    d3 = decide(qualified_state(), ext(intent="asks_advice"))
    assert d3.action == Action.ADVICE_DEFLECT_LATE


def test_masterclass_request_sets_flag():
    d = decide(empty_lead_state(), ext(intent="asks_masterclass"))
    assert d.action == Action.MASTERCLASS_SEND
    assert d.lead_state["flags"]["masterclass_sent"] is True


def test_phone_request_deflects():
    d = decide(empty_lead_state(), ext(intent="asks_phone"))
    assert d.action == Action.PHONE_NUMBER_DEFLECT


def test_same_question_three_times_hands_to_human():
    # Lead never resolves the financial question -> after two asks, hand to a human
    # instead of repeating it a third time (the test_2 bug).
    slots = {"trying_duration": "1y", "age": 34, "treatment_path": "natural",
             "priority_score": 9, "open_to_holistic": True}
    st = state(slots=slots, flags={"explained_role": True})
    d1 = decide(st, ext(intent="answers_question"))
    assert d1.action == Action.FINANCIAL_CHECK
    d2 = decide(d1.lead_state, ext(intent="answers_question"))
    assert d2.action == Action.FINANCIAL_CHECK
    d3 = decide(d2.lead_state, ext(intent="answers_question"))
    assert d3.action == Action.HUMAN_TAKEOVER
    assert d3.pause is True and d3.pause_reason == "stuck_repeating"


def test_partner_decision_during_financial_advances_not_loops():
    # "I'll have to ask my partner" -> partner is decision-maker (financial_ready
    # stays unset, as the extractor really returns) -> move to the partner step,
    # not re-ask the financial question.
    slots = {"trying_duration": "1y", "age": 34, "treatment_path": "natural",
             "priority_score": 9, "open_to_holistic": True}
    st = state(slots=slots, flags={"explained_role": True})
    e = ext(intent="answers_question", partner_status="couple", partner_is_decision_maker=True)
    d = decide(st, e)
    assert d.action == Action.PARTNER_ASK_JOIN


def test_partner_decision_maker_books_when_partner_will_join():
    # Money decision is the partner's; once they will join the call, the gate is met
    # even without an explicit personal financial confirmation.
    slots = {"trying_duration": "1y", "age": 34, "treatment_path": "natural",
             "priority_score": 9, "open_to_holistic": True,
             "partner_status": "couple", "partner_is_decision_maker": True,
             "partner_can_join": True}
    st = state(slots=slots, flags={"explained_role": True})
    d = decide(st, ext(intent="answers_question"))
    assert d.action == Action.SEND_BOOKING


def test_partner_decision_maker_blocked_if_cannot_afford():
    # Explicit "can't afford" still blocks even when partner is the decision-maker.
    slots = {"trying_duration": "1y", "age": 34, "treatment_path": "natural",
             "priority_score": 9, "open_to_holistic": True,
             "partner_status": "couple", "partner_is_decision_maker": True,
             "partner_can_join": True, "financial_ready": False}
    st = state(slots=slots, flags={"explained_role": True})
    d = decide(st, ext(intent="answers_question"))
    assert d.action != Action.SEND_BOOKING


def test_progressing_questions_do_not_trip_loop_guard():
    # Each turn asks a different question -> never a false takeover.
    st = empty_lead_state()
    d1 = decide(st, ext(intent="shares_situation", trying_duration="1 year"))
    assert d1.action == Action.ASK_DISCOVERY
    d2 = decide(d1.lead_state, ext(intent="answers_question", age=34))
    assert d2.action == Action.ASK_DISCOVERY  # now asks treatment path, different key
    d3 = decide(d2.lead_state, ext(intent="answers_question", treatment_path="natural"))
    assert d3.action == Action.ASK_PRIORITY
    assert d3.action != Action.HUMAN_TAKEOVER


def test_ivf_only_offer_then_continue():
    d1 = decide(empty_lead_state(), ext(intent="ivf_only"))
    assert d1.action == Action.IVF_ONLY_OFFER
    # Once interested, the offer is not repeated -> funnel resumes (discovery).
    d2 = decide(state(slots={"ivf_interest": True}), ext(intent="ivf_only"))
    assert d2.action == Action.ASK_DISCOVERY
