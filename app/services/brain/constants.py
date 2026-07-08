"""Shared vocabulary for the qualification-funnel brain.

These enums and the lead-state factory are the contract between the extractor
(Step 3), the flow controller (Step 4), the script registry (Step 2), the
composer (Step 5), and the validator (Step 6). Keep them stable.
"""
from enum import Enum


class Phase(str, Enum):
    """Where a lead sits in the qualification funnel."""
    OPENING = "OPENING"            # no message yet / awaiting first reply
    DISCOVERY = "DISCOVERY"        # light discovery questions
    PRIORITY = "PRIORITY"          # 1-10 priority qualification
    EXPLAIN_ROLE = "EXPLAIN_ROLE"  # confirm they understand what Sonia does
    FINANCIAL = "FINANCIAL"        # paid-program readiness
    PARTNER = "PARTNER"            # partner / decision-maker check
    BOOKING = "BOOKING"            # ready to send / just sent the link
    POST_BOOKING = "POST_BOOKING"  # collect email, send prep
    OOS = "OOS"                    # out of scope (terminal)
    TAKEOVER = "TAKEOVER"          # handed to a human (terminal)


class Action(str, Enum):
    """The single thing the controller decides to do on a turn.

    Every action except ASK_DISCOVERY maps to a verbatim template in the
    script registry. ASK_DISCOVERY is the only generative (composed) action.
    """
    # Discovery / flow
    PHASE1_OPENING = "PHASE1_OPENING"
    ASK_DISCOVERY = "ASK_DISCOVERY"            # composed (LLM)
    ASK_PRIORITY = "ASK_PRIORITY"
    PRIORITY_NOT_UNDERSTOOD = "PRIORITY_NOT_UNDERSTOOD"
    REENGAGE_LOW_PRIORITY = "REENGAGE_LOW_PRIORITY"
    LOW_PRIORITY_INFO_GATHERING = "LOW_PRIORITY_INFO_GATHERING"
    NURTURE_CLOSE = "NURTURE_CLOSE"  # not ready -> masterclass + soft goodbye, then end

    # Explain role
    EXPLAIN_ROLE = "EXPLAIN_ROLE"
    EXPLAIN_ROLE_TFS_UPDATED = "EXPLAIN_ROLE_TFS_UPDATED"
    EXPLAIN_ROLE_TFS1 = "EXPLAIN_ROLE_TFS1"
    EXPLAIN_ROLE_TFS2 = "EXPLAIN_ROLE_TFS2"
    EXPLAIN_ROLE_TFS3 = "EXPLAIN_ROLE_TFS3"
    EXPLAIN_ROLE_CONFIRM = "EXPLAIN_ROLE_CONFIRM"  # short re-ask of the fit question

    # Financial
    FINANCIAL_CHECK = "FINANCIAL_CHECK"
    FINANCIAL_DECLINE = "FINANCIAL_DECLINE"

    # Partner
    PARTNER_CHECK = "PARTNER_CHECK"
    PARTNER_ASK_JOIN = "PARTNER_ASK_JOIN"
    PARTNER_PUSHBACK = "PARTNER_PUSHBACK"
    SOLO_NO_PARTNER_ACK = "SOLO_NO_PARTNER_ACK"  # solo/donor -> no partner needed + stage question

    # Booking
    SEND_BOOKING = "SEND_BOOKING"
    BOOKING_IS_IT_SONIA = "BOOKING_IS_IT_SONIA"
    BOOKING_CALL_PROCESS = "BOOKING_CALL_PROCESS"
    BOOKING_WHO_NATALIA = "BOOKING_WHO_NATALIA"
    BOOKING_WHO_MONIKA = "BOOKING_WHO_MONIKA"

    # Post-booking
    POST_BOOKING_ASK_EMAIL = "POST_BOOKING_ASK_EMAIL"
    POST_BOOKING_CONFIRM_NATALIA = "POST_BOOKING_CONFIRM_NATALIA"
    POST_BOOKING_CONFIRM_MONIKA = "POST_BOOKING_CONFIRM_MONIKA"

    # Advice / price / misc deflections
    ADVICE_DEFLECT = "ADVICE_DEFLECT"                    # early (re-asks discovery)
    ADVICE_DEFLECT_LATE = "ADVICE_DEFLECT_LATE"          # discovery done (no re-ask)
    ADVICE_DEFLECT_PUSH = "ADVICE_DEFLECT_PUSH"          # early, keeps pushing
    ADVICE_DEFLECT_PUSH_LATE = "ADVICE_DEFLECT_PUSH_LATE"  # discovery done, keeps pushing
    PRICE_DEFLECT = "PRICE_DEFLECT"                      # 1st ask, discovery incomplete
    PRICE_DEFLECT_LATE = "PRICE_DEFLECT_LATE"            # 1st ask, discovery complete
    PRICE_RANGE = "PRICE_RANGE"                          # 2nd ask: reveal the range
    PRICE_RANGE_FIRM = "PRICE_RANGE_FIRM"                # 3rd+ ask: restate, push to call
    PHONE_NUMBER_DEFLECT = "PHONE_NUMBER_DEFLECT"
    MASTERCLASS_SEND = "MASTERCLASS_SEND"
    SOCIAL_PROOF = "SOCIAL_PROOF"
    PAYING_TWICE = "PAYING_TWICE"
    IVF_ONLY_OFFER = "IVF_ONLY_OFFER"
    TROUBLE_BOOKING = "TROUBLE_BOOKING"
    OLD_CONVO = "OLD_CONVO"
    COLD_OUTREACH = "COLD_OUTREACH"
    NO_MONEY = "NO_MONEY"

    # Out-of-scope clarifying questions + terminal messages
    ASK_BOTH_TUBES = "ASK_BOTH_TUBES"
    ONE_TUBE_ACK = "ONE_TUBE_ACK"  # one tube blocked -> acknowledge + stage question
    ASK_MENOPAUSE_REASON = "ASK_MENOPAUSE_REASON"
    ASK_MENOPAUSE_AGE = "ASK_MENOPAUSE_AGE"
    OOS_BOTH_TUBES = "OOS_BOTH_TUBES"
    OOS_MENOPAUSE = "OOS_MENOPAUSE"
    OOS_NO_PERIOD_12M = "OOS_NO_PERIOD_12M"  # 12+ months no period -> review, any age
    OOS_AGE_OVER_46 = "OOS_AGE_OVER_46"
    OOS_DEAF = "OOS_DEAF"

    # Terminal: hand to human, send nothing
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"  # not en/es -> silent handoff


class Intent(str, Enum):
    """What the lead's latest message is doing (classified by the extractor)."""
    SHARES_SITUATION = "shares_situation"
    ANSWERS_QUESTION = "answers_question"
    ASKS_PRICE = "asks_price"
    ASKS_ADVICE = "asks_advice"
    ASKS_WHAT_YOU_DO = "asks_what_you_do"
    ASKS_RESULTS_PROOF = "asks_results_proof"
    ASKS_PHONE = "asks_phone"
    ASKS_MASTERCLASS = "asks_masterclass"
    ASKS_IS_IT_SONIA = "asks_is_it_sonia"
    ASKS_CALL_PROCESS = "asks_call_process"
    READY_TO_BOOK = "ready_to_book"
    BOOKED = "booked"
    GIVES_EMAIL = "gives_email"
    TROUBLE_BOOKING = "trouble_booking"
    OBJECTION = "objection"
    PAYING_TWICE = "paying_twice"
    BLOCKED_TUBES = "blocked_tubes"
    MENOPAUSE_NO_PERIOD = "menopause_no_period"
    IVF_ONLY = "ivf_only"
    DEAF = "deaf"
    IS_THIS_AI = "is_this_ai"
    ANGRY_OR_CHALLENGING = "angry_or_challenging"
    DISTRESS = "distress"
    NOT_READY_NO_MONEY = "not_ready_no_money"
    OTHER = "other"


# --- Lead-state schema -------------------------------------------------------

SLOT_KEYS = [
    "trying_duration",          # free text, e.g. "2 years"
    "age",                      # int or free text
    "treatment_path",           # natural | iui | ivf | deciding
    "what_tried",               # free text / list
    "done_testing",             # True | False
    "diagnosis",                # none | suspected | confirmed
    "diagnosis_detail",         # free text
    "priority_score",           # int 1-10
    "strong_readiness",         # True when they clearly confirm readiness
    "understands_role",         # True after they accept the explain-role message
    "open_to_holistic",         # True when open to the holistic approach
    "financial_ready",          # True | False
    "partner_status",           # couple | solo | donor | single_by_choice
    "partner_is_decision_maker",
    "partner_can_join",
    "email_collected",          # the email string
    "closer_assigned",          # natalia | monika
    "tubes_blocked",            # none | one | both | unspecified (count unknown)
    "no_period_reason",         # free text (menopause assessment)
    "no_period_over_year",      # True when she states 12+ months without a period
    "ivf_interest",             # True when they accept IVF-optimization help
    "language",                 # en | es (sticky; None means not yet observed -> en)
]

FLAG_KEYS = [
    "booking_sent",
    "masterclass_sent",
    "explained_role",   # we have shown the explain-role message
    "asked_priority",   # we have asked the 1-10 question
    "situation_shared",
    "handed_off",       # booking sequence complete -> handed to a human
    "cost_declined",    # she said she can't afford it -> takeover if she keeps engaging
    "last_prompt",      # loop guard: key of the last question we sent
    "oos_reason",
    "takeover_reason",
]

COUNTER_KEYS = [
    "price_ask_count",
    "advice_push_count",
    "priority_reengage_count",
    "repeat_count",     # loop guard: consecutive identical questions
]

_DEFAULT_FLAGS = {
    "booking_sent": False,
    "masterclass_sent": False,
    "explained_role": False,
    "asked_priority": False,
    "situation_shared": False,
    "handed_off": False,
    "cost_declined": False,
    "last_prompt": None,
    "oos_reason": None,
    "takeover_reason": None,
}


def empty_lead_state() -> dict:
    """A fresh lead's state. The controller treats this as the OPENING phase."""
    return {
        "phase": Phase.OPENING.value,
        "slots": {k: None for k in SLOT_KEYS},
        "flags": dict(_DEFAULT_FLAGS),
        "counters": {k: 0 for k in COUNTER_KEYS},
    }


# Control flags cleared when a human resumes the AI after a takeover. Facts
# (slots) and progress flags (booking_sent, explained_role, ...) survive so
# the funnel picks up where it left off instead of restarting.
_RESUME_CLEARED_FLAGS = {
    "handed_off": False,
    "cost_declined": False,
    "last_prompt": None,
    "oos_reason": None,
    "takeover_reason": None,
}


def resume_lead_state(state: dict | None) -> dict:
    """Re-arm a lead after a human takeover: clear the terminal/control flags
    that would keep the brain silent (or instantly re-trigger a takeover) while
    preserving every extracted fact and funnel-progress flag."""
    base = normalize_lead_state(state)
    base["flags"].update(_RESUME_CLEARED_FLAGS)
    base["counters"]["repeat_count"] = 0
    return base


def normalize_lead_state(state: dict | None) -> dict:
    """Merge a persisted (possibly partial / older-schema) state onto defaults.

    Guarantees every slot/flag/counter key exists so downstream code never
    KeyErrors on a lead saved before a schema addition.
    """
    base = empty_lead_state()
    if not state:
        return base
    if state.get("phase"):
        base["phase"] = state["phase"]
    for group in ("slots", "flags", "counters"):
        for k, v in (state.get(group) or {}).items():
            if k in base[group]:
                base[group][k] = v
    return base
