"""Flow Controller — the deterministic heart of the brain. NO LLM.

Given the lead's current state and the extractor's structured reading of the
latest message, it (1) merges new facts into the state, (2) decides the SINGLE
next Action, and (3) builds the composer brief for the one generative action
(ASK_DISCOVERY). Every spec IF/THEN lives here, including the Phase-7 booking
gate. Because flow is code — not LLM judgment — the bot cannot book early,
cannot skip qualification, and cannot re-ask an answered question.
"""
from dataclasses import dataclass, field
from typing import Optional

from app.services.brain.constants import (
    Action,
    Phase,
    normalize_lead_state,
)
from app.services.brain.extractor import Extraction, non_null_deltas
from app.services.brain import scripts
# The qualification gates and OOS rules live in gates.py so every brain version
# shares one implementation. Re-exported here because `directive.py` and the
# controller tests reach for them as `controller._discovery_complete` etc.
from app.services.brain.gates import (  # noqa: F401
    _actively_ttc,
    _booking_action,
    _discovery_complete,
    _financial_ok,
    _partner_resolved,
    _priority_ok,
    _role_ok,
    booking_gate,
    oos_check,
)


@dataclass
class Decision:
    action: Action
    next_phase: str
    lead_state: dict
    composer_brief: Optional[dict] = None
    send_message: bool = True       # HUMAN_TAKEOVER sends nothing
    pause: bool = False             # stop the AI (OOS / takeover)
    pause_reason: Optional[str] = None
    add_tag: bool = False           # flag for human review in ManyChat
    qualified: bool = False         # booking complete -> "qualified / link sent" tag
    prompt_key: Optional[str] = None  # loop-guard identity of a question turn
    meta: dict = field(default_factory=dict)


# Questions that wait on a specific answer; asking one a third time in a row
# means the lead is stuck/confused, so we hand to a human instead of repeating.
_GATE_QUESTIONS = {
    Action.ASK_PRIORITY,
    Action.EXPLAIN_ROLE,
    Action.EXPLAIN_ROLE_CONFIRM,
    Action.FINANCIAL_CHECK,
    Action.PARTNER_CHECK,
    Action.PARTNER_ASK_JOIN,
    Action.SOLO_NO_PARTNER_ACK,
    Action.ASK_BOTH_TUBES,
    Action.ONE_TUBE_ACK,
    Action.ASK_MENOPAUSE_REASON,
    Action.ASK_MENOPAUSE_AGE,
    Action.ASK_DISCOVERY,
}


# Intents that are interrupts: answer them, then resume the funnel where it was.
# (Intents NOT listed here are funnel answers and fall through to the waterfall.)
_INTERRUPTS = {
    "asks_price", "asks_advice", "asks_what_you_do", "asks_results_proof",
    "asks_phone", "asks_masterclass", "paying_twice", "asks_is_it_sonia",
    "asks_call_process", "trouble_booking", "ivf_only", "objection",
    "not_ready_no_money",
}

# Intents that are ALWAYS a human takeover per the spec. Checked from the
# extracted intent label so the trigger never depends on the LLM also
# remembering to set the takeover boolean (same lesson as the age-48 miss).
_TAKEOVER_INTENTS = {"is_this_ai", "angry_or_challenging", "distress"}

# Discovery questions in priority order; the first missing slot is asked next.
_DISCOVERY_ORDER = ["trying_duration", "age", "treatment_path", "done_testing", "diagnosis"]

# Situation facts that count as "newly shared" for the reflect-back rule
# (Sonia v1.1: a multi-fact message must be reflected before the next question).
_FACT_DELTA_KEYS = ("trying_duration", "age", "treatment_path", "what_tried",
                    "done_testing", "diagnosis_detail")


# --- State merge -------------------------------------------------------------

def merge(lead_state: dict, extraction: Extraction) -> dict:
    state = normalize_lead_state(lead_state)
    deltas = non_null_deltas(extraction.slot_deltas)
    # "He won't join" is where the extractor over-infers who decides, in BOTH
    # directions: it reads "my husband can't make it" as either sole-decision-maker
    # (False) or, merely because a husband exists, as a shared decision (True). A
    # refusal says nothing about who decides, so it may not set the fact either
    # way. Dropping the delta leaves it null, which we treat as "he shares the
    # decision" -> the couples message. Only a value she volunteered on an EARLIER
    # turn ("I decide this myself") survives and gets her the plain link.
    if (deltas.get("partner_can_join") is False
            and deltas.get("partner_is_decision_maker") is not None):
        deltas.pop("partner_is_decision_maker")
    for k, v in deltas.items():
        if k in state["slots"]:
            state["slots"][k] = v
    s = state["slots"]
    # A partner fact without a partner_status means she referenced a partner
    # (the extractor can only learn these from partner mentions) -> couple.
    if s.get("partner_status") is None and (
        s.get("partner_can_join") is not None
        or s.get("partner_is_decision_maker") is not None
    ):
        s["partner_status"] = "couple"
    if _actively_ttc(s):
        state["flags"]["situation_shared"] = True
    return state


def assign_closer(cfg: Optional[dict], ig_user_id: str) -> str:
    cfg = cfg or {}
    mode = (cfg.get("closer_assignment") or "").strip().lower()
    if mode == "round_robin":
        return "natalia" if (sum(map(ord, ig_user_id)) % 2 == 0) else "monika"
    default = (cfg.get("default_closer") or "natalia").strip().lower()
    return default if default in ("natalia", "monika") else "natalia"


# --- Decision ----------------------------------------------------------------

def decide(
    lead_state: dict,
    extraction: Extraction,
    cfg: Optional[dict] = None,
    ig_user_id: str = "",
) -> Decision:
    # Captured BEFORE merge: "my doctor said IVF is my only option" can over-set
    # ivf_interest this same turn, which must not skip the IVF_ONLY_OFFER.
    prior_ivf_interest = (((lead_state or {}).get("slots")) or {}).get("ivf_interest")
    state = merge(lead_state, extraction)
    s, f, c = state["slots"], state["flags"], state["counters"]
    intent = extraction.intent

    # 0) Conversation already ended (booked, or nurtured-out) -> stay silent.
    if f.get("handed_off"):
        return _ended(state)

    # 0b) She already said she can't afford it and is still messaging -> that is
    # the "cannot afford but keeps engaging" takeover trigger from the spec.
    if f.get("cost_declined"):
        return _takeover(state, "cant_afford_engaging")

    # 1) Language. Sticky slot: only a confident read updates it; short/ambiguous
    # turns ("ok", "si", a number) keep the current value. An unsupported
    # language must be checked BEFORE the OOS declines below — those are
    # outgoing en/es text, and a lead we can't talk to gets silence, not a
    # decline she can't read. "other" does not overwrite the sticky slot.
    lang = extraction.language
    if lang in ("en", "es"):
        s["language"] = lang
    elif lang == "other":
        return _takeover(state, "unsupported_language", action=Action.UNSUPPORTED_LANGUAGE)

    # 2) Hard out-of-scope (gates.oos_check). The EXTRACTED FACTS are checked
    # before the LLM's signal so these never depend on the model remembering to
    # set a flag. A "clarify" outcome is a normal question and the funnel
    # continues; None means nothing tripped.
    outcome = oos_check(
        state,
        delta_tubes_blocked=extraction.slot_deltas.tubes_blocked,
        oos_signal=extraction.oos_signal,
    )
    if outcome is not None:
        if outcome.kind == "oos":
            return _oos(state, outcome.action, outcome.reason)
        return _script(state, outcome.action, outcome.phase)

    # 3) Human-takeover: from the intent label deterministically (asks-if-AI /
    # angry / severe distress), or the extractor's soft takeover flag.
    if intent in _TAKEOVER_INTENTS:
        return _takeover(state, extraction.takeover_reason or intent)
    if extraction.takeover:
        return _takeover(state, extraction.takeover_reason or "complex_case")

    # 3b) The booking link is out. From here the AI handles exactly two turns it
    # can handle safely - "I booked" and the email she booked with - and hands
    # everything else to a human. Deliberately ABOVE the interrupts: once she has
    # the link we stop deflecting price/call questions and let a person take it.
    if f.get("booking_sent"):
        return _post_booking(state, intent)

    # 4) Intent interrupts — answer, then stay put.
    if intent in _INTERRUPTS:
        decision = _handle_interrupt(state, intent, cfg, prior_ivf_interest)
        if decision is not None:
            return _guard_repeats(state, decision)
        # ivf_only when already interested falls through to the funnel.

    # 4b) She just said she is doing this on her own (solo / donor / single by
    # choice) -> explicitly reassure her no partner is needed on the call, then
    # ask her stage (Sonia v1.1). Delta-keyed; skipped once her stage is known.
    if extraction.slot_deltas.partner_status in ("solo", "donor", "single_by_choice") and not (
        s.get("treatment_path") or s.get("what_tried")
    ) and not f.get("booking_sent"):
        return _guard_repeats(state, _script(state, Action.SOLO_NO_PARTNER_ACK, Phase.DISCOVERY))

    # 5) The qualification waterfall.
    decision = _waterfall(state, cfg, ig_user_id, extraction.situation_type)
    deltas = non_null_deltas(extraction.slot_deltas)
    decision.meta["new_facts"] = [k for k in _FACT_DELTA_KEYS if k in deltas]
    return _guard_repeats(state, decision)


def _guard_repeats(state: dict, decision: Decision) -> Decision:
    """Never ask the same question a third time in a row. If we are about to,
    the lead is stuck or confused -> hand to a human (a spec takeover trigger)."""
    if decision.action not in _GATE_QUESTIONS:
        state["flags"]["last_prompt"] = None
        state["counters"]["repeat_count"] = 0
        return decision
    key = decision.prompt_key or decision.action.value
    if key == state["flags"].get("last_prompt"):
        repeat = state["counters"].get("repeat_count", 0) + 1
        if repeat >= 2:  # this would be the third identical prompt
            return _takeover(state, "stuck_repeating")
        state["counters"]["repeat_count"] = repeat
    else:
        state["counters"]["repeat_count"] = 0
    state["flags"]["last_prompt"] = key
    return decision


def _handle_interrupt(state: dict, intent: str, cfg: Optional[dict],
                      prior_ivf_interest: Optional[bool] = None) -> Optional[Decision]:
    s, f, c = state["slots"], state["flags"], state["counters"]

    if intent == "asks_price":
        # Engaging with cost signals financial openness -> don't re-ask the
        # financial question later (unless she explicitly declines on price).
        if s.get("financial_ready") is None:
            s["financial_ready"] = True
        c["price_ask_count"] = c.get("price_ask_count", 0) + 1
        n = c["price_ask_count"]
        if n >= 3:
            return _script(state, Action.PRICE_RANGE_FIRM)
        if n == 2:
            return _script(state, Action.PRICE_RANGE)
        # First ask: deflect without re-asking facts they've already shared.
        return _script(state, Action.PRICE_DEFLECT_LATE if _discovery_complete(s) else Action.PRICE_DEFLECT)
    if intent == "asks_advice":
        push = c.get("advice_push_count", 0)
        c["advice_push_count"] = push + 1
        complete = _discovery_complete(s)
        if push >= 1:
            return _script(state, Action.ADVICE_DEFLECT_PUSH_LATE if complete else Action.ADVICE_DEFLECT_PUSH)
        return _script(state, Action.ADVICE_DEFLECT_LATE if complete else Action.ADVICE_DEFLECT)
    if intent == "asks_what_you_do":
        f["explained_role"] = True
        return _script(state, Action.EXPLAIN_ROLE, Phase.EXPLAIN_ROLE)
    if intent == "asks_results_proof":
        return _script(state, Action.EXPLAIN_ROLE_TFS3)
    if intent == "asks_phone":
        return _script(state, Action.PHONE_NUMBER_DEFLECT)
    if intent == "asks_masterclass":
        f["masterclass_sent"] = True
        return _script(state, Action.MASTERCLASS_SEND)
    if intent == "paying_twice":
        return _script(state, Action.PAYING_TWICE)
    if intent == "asks_is_it_sonia":
        return _script(state, Action.BOOKING_IS_IT_SONIA)
    if intent == "asks_call_process":
        return _script(state, Action.BOOKING_CALL_PROCESS)
    if intent == "trouble_booking":
        return _script(state, Action.TROUBLE_BOOKING)
    if intent == "not_ready_no_money":
        # First cost decline -> masterclass (Sonia v1.1: free-only leads get
        # the free resource, never a bare goodbye); if she keeps engaging,
        # step 0b hands off to a human.
        f["cost_declined"] = True
        f["masterclass_sent"] = True
        return _script(state, Action.NO_MONEY)
    if intent == "objection":
        return _script(state, Action.SOCIAL_PROOF)
    if intent == "ivf_only":
        # Gate on the PRIOR state, not the merged one: this turn's extraction
        # can over-read "doctor said IVF is my only option" as acceptance.
        if prior_ivf_interest is not True:
            return _script(state, Action.IVF_ONLY_OFFER)
        return None  # already interested -> continue funnel
    return None


def _waterfall(
    state: dict, cfg: Optional[dict], ig_user_id: str, situation_type: str = "none"
) -> Decision:
    s, f, c = state["slots"], state["flags"], state["counters"]

    # DISCOVERY
    if not _discovery_complete(s):
        missing = next((k for k in _DISCOVERY_ORDER if not s.get(k)), "trying_duration")
        return _ask_discovery(state, missing, situation_type)

    # PRIORITY
    if not _priority_ok(s):
        score = s.get("priority_score")
        low_score = isinstance(score, int) and score < 8
        step = c.get("priority_reengage_count", 0)
        if not f.get("asked_priority"):
            f["asked_priority"] = True
            return _script(state, Action.ASK_PRIORITY, Phase.PRIORITY)
        # Emotional / vague reply with no number (and not yet escalating): that is
        # not a low score -> acknowledge and gently re-ask, never a sales pitch.
        if score is None and not low_score and step == 0:
            return _script(state, Action.ASK_PRIORITY, Phase.PRIORITY)
        # Low score (or persistent non-engagement) -> escalate through fixed steps,
        # then soft-close. This can never loop forever (the test_2 bug).
        if step == 0:
            c["priority_reengage_count"] = 1
            return _script(state, Action.REENGAGE_LOW_PRIORITY, Phase.PRIORITY)
        if step == 1:
            c["priority_reengage_count"] = 2
            return _script(state, Action.LOW_PRIORITY_INFO_GATHERING, Phase.PRIORITY)
        # Re-engaged + probed and still not ready -> masterclass + soft goodbye, end.
        return _nurture_close(state)

    # EXPLAIN ROLE — she must understand the not-a-doctor role. Her own words
    # ("I understand this is coaching, not medical care") satisfy it without
    # re-running the role step (Sonia v1.1: the one-message qualified lead);
    # otherwise explain once, then confirm she wants this kind of support.
    if not _role_ok(state):
        if not f.get("explained_role"):
            f["explained_role"] = True
            return _script(state, Action.EXPLAIN_ROLE, Phase.EXPLAIN_ROLE)
        if s.get("open_to_holistic") is False:
            return _script(state, Action.SOCIAL_PROOF, Phase.EXPLAIN_ROLE)
        return _script(state, Action.EXPLAIN_ROLE_CONFIRM, Phase.EXPLAIN_ROLE)

    # FINANCIAL
    if not _financial_ok(s):
        if s.get("financial_ready") is False:
            f["cost_declined"] = True
            return _script(state, Action.FINANCIAL_DECLINE, Phase.FINANCIAL)
        # If the partner is the decision-maker, the money decision happens with
        # them on the call -> fall through to partner handling instead of asking
        # the lead to confirm it alone.
        if s.get("partner_is_decision_maker") is not True:
            return _script(state, Action.FINANCIAL_CHECK, Phase.FINANCIAL)

    # PARTNER. Two questions at most: is there a partner, and can he come? If he
    # cannot, we do NOT go on to ask who decides - we assume he shares it and
    # book her with the couples expectation set (_booking_action).
    if not _partner_resolved(s):
        if s.get("partner_status") is None:
            f["asked_partner"] = True
            return _script(state, Action.PARTNER_CHECK, Phase.PARTNER)
        f["asked_partner_join"] = True
        return _script(state, Action.PARTNER_ASK_JOIN, Phase.PARTNER)

    # BOOKING -> send the link and tag her as qualified, but stay LIVE: Sonia v1.2
    # wants the AI to keep going and collect the booking email, so this no longer
    # pauses or hands off.
    if booking_gate(state):
        f["booking_sent"] = True
        decision = _script(state, _booking_action(s), Phase.BOOKING)
        decision.add_tag = True
        decision.qualified = True
        return decision
    # Safety net: gate not met though the waterfall passed. Re-discover.
    return _ask_discovery(state, "trying_duration", situation_type)


# --- Decision constructors ---------------------------------------------------

def _script(state: dict, action: Action, phase: Optional[Phase] = None) -> Decision:
    if phase is not None:
        state["phase"] = phase.value
    return Decision(action=action, next_phase=state["phase"], lead_state=state,
                    prompt_key=action.value)


def _ask_discovery(state: dict, missing_slot: str, situation_type: str = "none") -> Decision:
    state["phase"] = Phase.DISCOVERY.value
    s = state["slots"]
    facts = {
        k: s[k]
        for k in ("trying_duration", "age", "treatment_path", "what_tried", "diagnosis_detail")
        if s.get(k)
    }
    es = s.get("language") == "es"
    empathy = scripts.EMPATHY_VARIANTS_ES if es else scripts.EMPATHY_VARIANTS
    questions = scripts.DISCOVERY_QUESTIONS_ES if es else scripts.DISCOVERY_QUESTIONS
    brief = {
        "empathy_line": empathy.get(situation_type),
        "facts_to_reflect": facts,
        "next_question": questions[missing_slot],
    }
    return Decision(
        action=Action.ASK_DISCOVERY,
        next_phase=state["phase"],
        lead_state=state,
        composer_brief=brief,
        prompt_key=f"ASK_DISCOVERY:{missing_slot}",
    )


def _oos(state: dict, action: Action, reason: str) -> Decision:
    state["phase"] = Phase.OOS.value
    state["flags"]["oos_reason"] = reason
    return Decision(
        action=action,
        next_phase=Phase.OOS.value,
        lead_state=state,
        pause=True,
        pause_reason=reason,
        add_tag=True,
    )


def _post_booking(state: dict, intent: str) -> Decision:
    """The booking link is out. Sonia v1.2: the AI only handles the two turns it
    can handle safely - "I booked" (send the prep message) and her email (confirm
    receipt, then hand over). ANY other message is a human's job, so it pauses:
    no price deflections, no nudging, no small talk once she has the link."""
    s = state["slots"]

    # Her email is proof she booked, whether or not the extractor caught the
    # "booked" intent and whether or not we ever got to ask for it.
    if s.get("email_collected"):
        return _booked_handoff(state)

    # She just told us she booked -> the prep message, exactly once. The phase
    # check is what stops it being replayed on a later turn.
    if intent == "booked" and state["phase"] != Phase.POST_BOOKING.value:
        return _script(state, Action.POST_BOOKING_ASK_EMAIL, Phase.POST_BOOKING)

    # Anything else after the link -> pause, a human takes it from here.
    return _takeover(state, "qualified_link_sent")


def _booked_handoff(state: dict) -> Decision:
    """Email captured -> confirm we received it (never claim the appointment is
    verified; the AI cannot see the calendar), then pause for a human. Reuses the
    existing "qualified / booking link sent" state so ops keeps one banner and one
    ManyChat tag rather than gaining a new one."""
    state["flags"]["handed_off"] = True
    state["flags"]["takeover_reason"] = "qualified_link_sent"
    decision = _script(state, Action.POST_BOOKING_ACK, Phase.POST_BOOKING)
    decision.pause = True
    decision.pause_reason = "qualified_link_sent"
    decision.add_tag = True
    decision.qualified = True
    return decision


def _nurture_close(state: dict) -> Decision:
    """Not ready after re-engagement -> send masterclass + soft goodbye, then end."""
    state["flags"]["handed_off"] = True
    state["flags"]["takeover_reason"] = "not_ready_nurture"
    decision = _script(state, Action.NURTURE_CLOSE, Phase.PRIORITY)
    decision.pause = True
    decision.pause_reason = "not_ready_nurture"
    decision.add_tag = True
    return decision


def _ended(state: dict) -> Decision:
    """The AI has already ended this conversation (booked or nurtured-out).
    Stay silent; do not re-send or re-tag."""
    state["phase"] = Phase.TAKEOVER.value
    return Decision(
        action=Action.HUMAN_TAKEOVER, next_phase=Phase.TAKEOVER.value, lead_state=state,
        send_message=False, pause=True,
        pause_reason=state["flags"].get("takeover_reason") or "conversation_ended",
        add_tag=False,
    )


def _takeover(state: dict, reason: str, action: Action = Action.HUMAN_TAKEOVER) -> Decision:
    state["phase"] = Phase.TAKEOVER.value
    state["flags"]["takeover_reason"] = reason
    return Decision(
        action=action,
        next_phase=Phase.TAKEOVER.value,
        lead_state=state,
        send_message=False,
        pause=True,
        pause_reason=reason,
        add_tag=True,
    )
