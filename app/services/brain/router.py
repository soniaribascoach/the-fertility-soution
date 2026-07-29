"""Router - decides WHAT THE REPLY IS FOR. Pure code, NO LLM.

This is the fix for the failure Sonia reported: the qualification funnel used to
be the only path through the brain, so a pregnancy announcement, a thank-you and
"I've decided to stop trying" all ended up being qualified.

Here QUALIFY is one of nine modes. Which one a turn gets is decided by code from
the classified intent, the conversation stage, and the existing gates - never by
model judgement, so "never qualify a grieving woman" is a property the tests can
prove rather than a phrase in a prompt.

Order matters and is deliberate; see `route`.
"""
from dataclasses import dataclass, field
from typing import Optional

from app.services.brain import gates
from app.services.brain.constants import (
    NEVER_QUALIFY,
    Action,
    LeadIntent,
    Phase,
    ResponseMode,
    Stage,
)
from app.services.brain.gates import OosOutcome


@dataclass
class Route:
    """The routing decision for one turn."""
    mode: ResponseMode
    intent: LeadIntent
    stage: Stage
    reason: str                      # why this mode - persisted for the trace
    lead_state: dict = field(default_factory=dict)

    # She asked something; it must be answered before any qualification move.
    answer_first: bool = False
    question_asked: Optional[str] = None

    # Side effects, same semantics as the funnel brain's Decision.
    send_message: bool = True
    pause: bool = False
    pause_reason: Optional[str] = None
    add_tag: bool = False
    qualified: bool = False

    # Set when the turn still runs through the funnel (QUALIFY / BOOK) or when an
    # out-of-scope rule pinned a specific approved script.
    funnel_action: Optional[Action] = None
    pinned_action: Optional[Action] = None


# Intents that go straight to a human, whatever else is true.
_ESCALATE = {
    LeadIntent.IS_THIS_AI: "asks_if_ai",
    LeadIntent.ANGRY_OR_CHALLENGING: "angry_or_challenging",
    LeadIntent.DISTRESS: "distress",
    LeadIntent.EXISTING_CLIENT: "existing_client",
    LeadIntent.COLLABORATION_OR_TECHNICAL: "collaboration_or_technical",
}

# Intents that are a question first and foremost. Sonia: "The prospect's question
# should be answered first. Qualification should only follow when it is relevant."
_QUESTION_INTENTS = {
    LeadIntent.GENERAL_FERTILITY_QUESTION: ResponseMode.ANSWER,
    LeadIntent.ASKS_FREE_ADVICE: ResponseMode.ANSWER,
    LeadIntent.ASKS_ABOUT_PROGRAM: ResponseMode.ANSWER,
    LeadIntent.ASKS_RESULTS_PROOF: ResponseMode.EDUCATE,
    LeadIntent.ASKS_MASTERCLASS: ResponseMode.RESOURCE,
}

# Objections are four different conversations. Sonia: "A financial concern, fear
# after repeated IVF failure, a husband who does not believe in coaching, and
# someone asking for free supplement advice are completely different situations."
_OBJECTION_INTENTS = {
    LeadIntent.OBJECTION_PRICE: ResponseMode.ANSWER,
    LeadIntent.OBJECTION_PARTNER: ResponseMode.ANSWER,
    LeadIntent.OBJECTION_PAYING_TWICE: ResponseMode.ANSWER,
    LeadIntent.OBJECTION_TRUST: ResponseMode.EDUCATE,
    # Fear after failure is acknowledged before anything is explained.
    LeadIntent.OBJECTION_FEAR_AFTER_FAILURE: ResponseMode.ACKNOWLEDGE,
}


def derive_stage(state: dict) -> Stage:
    """Where the conversation is, independent of why this message was sent."""
    f = state["flags"]
    if f.get("handed_off"):
        return Stage.BOOKED
    if state["slots"].get("email_collected"):
        return Stage.BOOKED
    if f.get("booking_sent"):
        return Stage.LINK_SENT
    if gates.booking_gate(state):
        return Stage.QUALIFIED
    if f.get("situation_shared"):
        return Stage.DISCOVERING
    return Stage.COLD


def _route(state, intent, stage, mode, reason, **kw) -> Route:
    return Route(mode=mode, intent=intent, stage=stage, reason=reason,
                 lead_state=state, **kw)


def _handoff(state, intent, stage, reason, *, send_message=False) -> Route:
    state["phase"] = Phase.TAKEOVER.value
    state["flags"]["takeover_reason"] = reason
    return _route(state, intent, stage, ResponseMode.HANDOFF, reason,
                  send_message=send_message, pause=True, pause_reason=reason,
                  add_tag=True)


def route(state: dict, classification, cfg: Optional[dict] = None) -> Route:
    """Pick the single response mode for this turn.

    The order below is the specification. Each step exists because something
    above it would otherwise swallow the case:

      1. already ended            - never speak again on a closed conversation
      2. unsupported language     - silence beats a decline she cannot read
      3. hard out-of-scope        - facts decide, not the model
      4. escalation intents       - a human's job regardless of funnel position
      5. cannot tell              - unsure or off-script goes to a human
      6. never-qualify intents    - THE fix: these bypass the funnel entirely
      7. after the link is out    - the AI handles two turns and hands over
      8. she asked something      - answer before qualifying
      9. objections               - four different conversations
     10. probably not a fit       - say so honestly instead of pitching
     11. ready and gated          - book
     12. otherwise                - qualify
    """
    s, f = state["slots"], state["flags"]
    intent = LeadIntent(classification.intent)
    stage = derive_stage(state)

    # 1) The conversation is already over (booked out, or nurtured out).
    if f.get("handed_off"):
        state["phase"] = Phase.TAKEOVER.value
        return _route(state, intent, stage, ResponseMode.HANDOFF, "conversation_ended",
                      send_message=False, pause=True,
                      pause_reason=f.get("takeover_reason") or "conversation_ended")

    # 2) Language. Sticky: only a confident read updates it. A lead we cannot
    # talk to gets silence plus a human, never a decline in a language she does
    # not read - so this precedes every outgoing script below.
    lang = classification.language
    if lang in ("en", "es"):
        s["language"] = lang
    elif lang == "other":
        return _handoff(state, intent, stage, "unsupported_language")

    # 3) Hard out-of-scope, from the extracted facts first so these never depend
    # on the model remembering to raise a flag.
    outcome = gates.oos_check(
        state,
        delta_tubes_blocked=classification.slot_deltas.tubes_blocked,
        oos_signal=classification.oos_signal,
    )
    if outcome is not None:
        return _oos_route(state, intent, stage, outcome)

    # 4) Straight to a human.
    if intent in _ESCALATE:
        return _handoff(state, intent, stage, _ESCALATE[intent])
    if classification.takeover:
        return _handoff(state, intent, stage,
                        classification.takeover_reason or "complex_case")

    # 4b) She said she cannot afford it and is still messaging.
    if f.get("cost_declined"):
        return _handoff(state, intent, stage, "cant_afford_engaging")

    # 5) We genuinely cannot tell what she wants. Sonia would rather a person
    # picked this up than have the bot guess.
    if classification.intent_certainty == "unsure":
        return _handoff(state, intent, stage, "intent_unclear")
    if classification.off_script:
        return _handoff(state, intent, stage, "off_script")

    # 6) THE FIX. These are not sales conversations and never become one.
    if intent is LeadIntent.PREGNANCY_OR_SUCCESS:
        return _route(state, intent, stage, ResponseMode.CELEBRATE, "pregnancy_or_success",
                      pause=True, pause_reason="celebrate_handoff", add_tag=True)
    if intent is LeadIntent.GRATITUDE:
        return _route(state, intent, stage, ResponseMode.ACKNOWLEDGE, "gratitude")
    if intent is LeadIntent.GRIEF_OR_STOPPED_TRYING:
        # Acknowledge, then stop. No masterclass redirect - Sonia calls that out
        # explicitly as template matching.
        return _route(state, intent, stage, ResponseMode.ACKNOWLEDGE, "grief_or_stopped_trying",
                      pause=True, pause_reason="grief_handoff", add_tag=True)
    if intent is LeadIntent.NOT_A_FIT_SIGNAL:
        return _route(state, intent, stage, ResponseMode.HONEST_DECLINE, "she_says_not_a_fit")

    # 7) The link is out. The AI handles exactly the two turns it can handle
    # safely and hands everything else over.
    if f.get("booking_sent"):
        return _post_booking(state, intent, stage)

    question = classification.question_asked

    # 8) She asked something. Answer it before any qualification move.
    if intent in _QUESTION_INTENTS:
        return _route(state, intent, stage, _QUESTION_INTENTS[intent], f"question:{intent.value}",
                      answer_first=True, question_asked=question)

    # 9) Objections, each its own conversation.
    if intent in _OBJECTION_INTENTS:
        if intent is LeadIntent.OBJECTION_PRICE:
            # Engaging with cost signals financial openness, so the financial
            # step is not re-asked later (unless she explicitly declines).
            if s.get("financial_ready") is None:
                s["financial_ready"] = True
            state["counters"]["price_ask_count"] = state["counters"].get("price_ask_count", 0) + 1
        return _route(state, intent, stage, _OBJECTION_INTENTS[intent],
                      f"objection:{intent.value}",
                      answer_first=bool(question), question_asked=question)

    # 10) Her own facts say she probably does not need this yet. Sonia wants her
    # told honestly rather than sold to.
    if gates.likely_not_a_fit(state):
        return _route(state, intent, stage, ResponseMode.HONEST_DECLINE, "likely_not_a_fit")

    # 11) Ready to move, and the gate agrees.
    if gates.booking_gate(state):
        f["booking_sent"] = True
        return _route(state, intent, Stage.QUALIFIED, ResponseMode.BOOK, "gate_passed",
                      funnel_action=gates._booking_action(s), add_tag=True, qualified=True)

    # 12) Everything else is the funnel.
    return _guard(_route(state, intent, stage, ResponseMode.QUALIFY, "qualify",
                         question_asked=question))


def _oos_route(state, intent, stage, outcome: OosOutcome) -> Route:
    if outcome.kind == "oos":
        state["phase"] = Phase.OOS.value
        state["flags"]["oos_reason"] = outcome.reason
        return _route(state, intent, Stage.COLD, ResponseMode.HANDOFF, outcome.reason,
                      pinned_action=outcome.action, pause=True,
                      pause_reason=outcome.reason, add_tag=True)
    # "clarify": a normal question, the funnel continues afterwards.
    if outcome.phase is not None:
        state["phase"] = outcome.phase.value
    return _route(state, intent, stage, ResponseMode.QUALIFY, f"clarify:{outcome.action.value}",
                  funnel_action=outcome.action)


def _post_booking(state, intent, stage) -> Route:
    """After the link: confirm the email, then a human takes over.

    Anything else - small talk, a price question, a second "I booked" - is a
    person's job. No deflections once she has the link.
    """
    if state["slots"].get("email_collected") or intent is LeadIntent.GIVES_EMAIL:
        state["flags"]["handed_off"] = True
        state["flags"]["takeover_reason"] = "qualified_link_sent"
        return _route(state, intent, Stage.BOOKED, ResponseMode.ACKNOWLEDGE, "booking_email_received",
                      funnel_action=Action.POST_BOOKING_ACK, pause=True,
                      pause_reason="qualified_link_sent", add_tag=True, qualified=True)

    if intent is LeadIntent.BOOKED and state["phase"] != Phase.POST_BOOKING.value:
        state["phase"] = Phase.POST_BOOKING.value
        return _route(state, intent, Stage.BOOKED, ResponseMode.ANSWER, "booked_ask_email",
                      funnel_action=Action.POST_BOOKING_ASK_EMAIL)

    return _handoff(state, intent, stage, "qualified_link_sent")


def _guard(route_: Route) -> Route:
    """Last line of defence: a never-qualify intent must never reach QUALIFY.

    Every such intent is handled explicitly above, so reaching here means a new
    intent was added without a branch. Failing to a human is the safe direction,
    and the test suite asserts this can never fire in practice.
    """
    if route_.mode is ResponseMode.QUALIFY and route_.intent in NEVER_QUALIFY:
        return _handoff(route_.lead_state, route_.intent, route_.stage,
                        f"unrouted_never_qualify:{route_.intent.value}")
    return route_
