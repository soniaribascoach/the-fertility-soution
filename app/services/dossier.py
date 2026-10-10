"""Lead memory, and the gates that decide what the writer is allowed to see.

Two jobs, both pure and both testable without an API key.

`merge` folds what the READ call extracted into the lead's running dossier, which is then rendered
straight back into the WRITE prompt as "what she has already told me". That block is the whole
answer to "the API has no context": memory is an explicit, growing record rather than something the
model has to re-derive from twenty messages every turn.

`gate` decides which `[[BLOCK:...]]` sections of the knowledge base this turn may contain. When a
turn must not invite a booking, the booking block is simply not rendered, the model has no link to
send. Nothing here inspects generated text, and nothing here matches a pattern against her prose:
every branch is a comparison against a typed value the reader extracted.
"""
from dataclasses import dataclass, field

# Phases are for admin visibility and for post-booking routing. Nothing branches on them except
# the post-booking block.
OPENING = "OPENING"
EXPLORING = "EXPLORING"
LINK_SENT = "LINK_SENT"
POST_BOOKING = "POST_BOOKING"

# Slots whose value is replaced when she restates it, vs. slots that accumulate.
SCALAR_SLOTS = (
    "age", "time_trying", "conceiving_mode", "ivf_history", "iui_history",
    "miscarriage_history", "partner_status", "donor_sperm", "attendance", "pregnancy_priority",
    "email", "goal_stated",
)
LIST_SLOTS = ("diagnoses", "already_tried", "testing_done")

# Any one of these hands the conversation to a person (2B.1 §10, 2B.2 §13). Order is priority:
# the first match names the reason, so the two safety flags come first.
#
# `needs_human` is the general one and the only one that needs to grow. The rest of the 2B.1 §10
# list (crisis, minors, a third party asking, medically complex history, contradictions, a
# conversation that has stopped moving) lives in `prompts_simple/read.md` as prose rather than
# here as flag names, so adding a route is an edit to a prompt and not a deploy.
#
# The flags that carry a fixed line come before `needs_human`, because a woman who asked to speak
# to a person and also tripped the general flag should still be told a person is coming.
#
# `asked_if_ai` is deliberately not here. Handing over the moment she asks made the question itself
# unanswerable: she asked whether she was talking to a person and the conversation went silent,
# which is the loudest possible yes and reads as a dodge. She is now told the truth and offered a
# person, and only her answer to that offer, which arrives as `asked_for_human`, hands over.
ESCALATION_FLAGS = (
    "crisis", "urgent_medical", "abusive", "asked_for_human", "needs_human",
    "requested_medication", "requested_surgery_advice", "is_existing_client", "is_former_client",
)
ESCALATION_INTENTS = (
    "complaint", "collaboration", "media_request", "spam_or_aggression", "technical_support",
    "opt_out",
)

# A handover turn never calls the writer, so nothing about it is generated. She gets one fixed line
# from config. By default that is the review acknowledgment (§F, 2B.2 §13), sent once on every
# review, age review included. Two reasons carry a safety line instead, because someone in crisis
# or bleeding needs more than "we'll take a closer look". Abuse stays silent, because an
# acknowledgment that thanks her for sharing would be absurd there, and so does a request to stop
# receiving messages, which a reply would ignore.
REVIEW_MESSAGE = "handover_message_review"
HANDOVER_MESSAGES = {
    "crisis": "handover_message_crisis",
    "urgent_medical": "handover_message_urgent_medical",
}
SILENT_HANDOVERS = ("abusive", "spam_or_aggression", "opt_out")

# Fertility prospects this age or over are reviewed by a person before the link (§B, 2B.1 §10).
# Never a rejection, and never applied to a pregnant woman asking about The Pregnancy Solution.
AGE_REVIEW = 48

# Structural findings that close off a booking entirely (2B.1 §6, §9).
BLOCKING_STRUCTURAL = ("no_uterus", "menopause")

SLOT_LABELS = {
    "age": "Age",
    "time_trying": "Trying for",
    "conceiving_mode": "Currently",
    "ivf_history": "IVF history",
    "iui_history": "IUI history",
    "miscarriage_history": "Losses",
    "diagnoses": "Diagnoses she has shared",
    "already_tried": "Already tried",
    "testing_done": "Testing done",
    "partner_status": "Partner",
    "donor_sperm": "Using donor sperm",
    "attendance": "Partner on the call",
    "pregnancy_priority": "How much of a priority pregnancy is",
    "email": "Email",
    "goal_stated": "What she says she wants",
}


@dataclass
class Gate:
    """What this turn is allowed to do."""
    allow_booking: bool = False
    escalate: bool = False
    escalate_reason: str = ""
    handover_message: str = ""        # config key of the fixed line to send, "" means send nothing
    blocks: set = field(default_factory=set)
    notes: list = field(default_factory=list)
    block_reason: str = ""
    silent: bool = False              # after the link, a message that needs no reply
    after_link: str = ""              # after the link, what this reply is for


def handover_message(reason: str) -> str:
    """The config key of the line a handover sends, "" for none."""
    if reason in SILENT_HANDOVERS:
        return ""
    return HANDOVER_MESSAGES.get(reason, REVIEW_MESSAGE)


# The reader is asked to omit what she did not say, and mostly does. When it does not, it says so
# in words: `partner_status: "unstated"`, `time_trying: "not stated"`. Those are the absence of a
# fact wearing the costume of one, and they cost twice. They count toward the "do I understand
# enough of her situation" threshold that decides whether a booking is honest, and they render into
# the writer's dossier under "what she has already told me", where "Trying for: not stated" reads
# as something she said.
_NOT_A_VALUE = {
    "", "-", "n/a", "na", "none", "null", "unknown", "unstated", "not stated", "not specified",
    "not mentioned", "not provided", "not given", "unspecified", "unclear", "tbd",
}


def _stated(value) -> bool:
    """Whether a slot holds something she actually told us."""
    if value in (None, "", []):
        return False
    if isinstance(value, str):
        return value.strip().lower().strip(".") not in _NOT_A_VALUE
    return True


def empty_state() -> dict:
    return {"phase": None, "slots": {}, "flags": {}, "counters": {}}


def merge(lead_state: dict | None, read: dict) -> dict:
    """Fold this turn's extraction into the running dossier."""
    state = {**empty_state(), **(lead_state or {})}
    slots = dict(state.get("slots") or {})
    flags = dict(state.get("flags") or {})
    counters = dict(state.get("counters") or {})

    new_slots = read.get("slots") or {}
    for key in SCALAR_SLOTS:
        value = new_slots.get(key)
        if _stated(value):
            slots[key] = value
    for key in LIST_SLOTS:
        incoming = new_slots.get(key) or []
        if isinstance(incoming, str):
            incoming = [incoming]
        incoming = [v for v in incoming if _stated(v)]
        if incoming:
            existing = slots.get(key) or []
            # Preserve order, drop repeats, she often restates a diagnosis in different words.
            seen = {str(v).strip().lower() for v in existing}
            slots[key] = existing + [v for v in incoming if str(v).strip().lower() not in seen]

    # Flags are sticky: once she has told us she will not pay for coaching, a later message that
    # simply does not mention it must not quietly clear that.
    for key, value in (read.get("flags") or {}).items():
        if value:
            flags[key] = True

    structural = (read.get("flags") or {}).get("structural") or read.get("structural")
    if structural:
        flags["structural"] = structural

    # A live pregnancy is a fact about her, not a property of the message that announced it. The
    # reader reports it as an intent, which only describes the turn it arrived on, so it is pinned
    # here alongside the other sticky boundary facts: she is still pregnant on the turn where she
    # asks what to eat.
    if read.get("intent") == "pregnancy_announcement":
        flags["currently_pregnant"] = True

    if read.get("language"):
        slots["language"] = read["language"]

    counters["turns"] = int(counters.get("turns", 0)) + 1
    counters["teaching"] = _teaching_run(state, read, counters)
    state.update(slots=slots, flags=flags, counters=counters)
    state.setdefault("phase", None)
    return state


# Intents that mean she asked about how fertility works rather than about herself.
TEACHING_INTENTS = ("free_info_request", "fertility_question", "ivf_question")


def _teaching_run(previous: dict, read: dict, counters: dict) -> int:
    """How many general questions in a row she has now asked.

    The prompt said to stop teaching and send the masterclass by the third one. That was in the
    prompt for five rounds and the spiral still ran to eight, because a rule about counting is
    being asked of a model that is not counting: it sees a reasonable question and answers it, and
    every answer is individually defensible.

    So the count is done here and handed to the writer as a fact about this turn. A question is
    general when the reader classified it as one and it told us nothing new about her, which is the
    same test the manual uses: "with nothing about her in either of them".
    """
    if read.get("intent") not in TEACHING_INTENTS:
        return 0
    learned = {
        key: value for key, value in (read.get("slots") or {}).items()
        if key != "language" and _stated(value)
    }
    if learned != {k: v for k, v in (previous.get("slots") or {}).items() if k in learned}:
        return 0
    return int(counters.get("teaching", 0)) + 1


def _escalation_reason(state: dict, read: dict, before: dict | None = None) -> str:
    """Why this turn goes to a person. Empty string means it does not.

    Only what is new this turn hands over: flags from this turn's read, facts only when this turn
    changed them (`before` is the pre-merge dossier). The pause keeps the AI quiet while the team
    has her, and after a resume an old reason must not send her straight back.
    """
    raised = read.get("flags") or {}
    flags = state.get("flags") or {}
    slots = state.get("slots") or {}

    def new(path: str, key: str) -> bool:
        return (state.get(path) or {}).get(key) != ((before or {}).get(path) or {}).get(key)

    for flag in ESCALATION_FLAGS:
        # An unsupported language names itself rather than disappearing into the general flag,
        # because the person picking the conversation up needs to know they will need Portuguese.
        if flag == "needs_human" and raised.get(flag) and slots.get("language") == "other":
            return "language_not_supported"
        if raised.get(flag):
            return flag

    if read.get("intent") in ESCALATION_INTENTS:
        return read["intent"]

    if slots.get("language") == "other" and new("slots", "language"):
        return "language_not_supported"

    if flags.get("structural") == "unclear_menopause" and new("flags", "structural"):
        return "menopause_unclear"

    return ""


def _pregnancy_prospect(state: dict) -> bool:
    """Pregnant and asking about The Pregnancy Solution: none of the fertility checks apply."""
    flags = state.get("flags") or {}
    return bool(flags.get("currently_pregnant") and flags.get("wants_pregnancy_support"))


def _booking_blocked(state: dict, read: dict) -> str:
    """Why this turn may not offer the link. Empty string means it may."""
    flags = state.get("flags") or {}
    slots = state.get("slots") or {}
    structural = flags.get("structural")

    # 2B.2 §10: a current client is never qualified or sold to.
    if flags.get("in_my_program"):
        return "in_my_program"
    if structural in BLOCKING_STRUCTURAL:
        return f"structural_{structural}"
    if structural == "unclear_tubal":
        return "tubal_status_unclear"
    if structural == "both_tubes" and (flags.get("wants_natural_only") or not flags.get("open_to_ivf")):
        return "both_tubes_without_ivf"
    if flags.get("refuses_paid_coaching"):
        return "refuses_paid_coaching"
    # This turn only, like the two below. Sticky, one demand shut the link for good: she accepted
    # the answer, asked to book twice and was told there was no link.
    if (read.get("flags") or {}).get("demands_guarantee"):
        return "demands_guarantee"
    # Read from this turn rather than from the dossier, and deliberately not sticky. "I'm planning
    # IVF in a month or two" is the sentence half of her audience opens with, and one reader misfire
    # on it used to shut the link for the whole conversation: every later turn was told to say what
    # she does not provide, so four messages were answered with four refusals and no question. What
    # she asked for on the turn she asked for it is still declined; what she asks next is a new
    # question.
    if (read.get("flags") or {}).get("wants_unprovided_service"):
        return "out_of_scope_request"
    if (read.get("flags") or {}).get("requested_lab_interpretation"):
        # Refusing to read her results and inviting her to a call in the same breath turns the
        # boundary into a sales lever, which is exactly what Appendix A warns against.
        return "lab_request"
    if flags.get("recent_loss"):
        return "recent_loss"

    # §A makes a woman who has stopped trying a terminal conversation: she is answered and the
    # conversation is allowed to end. There is nothing to sell someone who is not trying, and the
    # flag is sticky, so this holds for the rest of the conversation and not only for the message
    # that said it.
    #
    # Below the loss on purpose. "We lost it at 11 weeks and we've decided that's it" sets both,
    # and grief is the more urgent fact of that message: the loss conversation stays with what
    # happened rather than with what she has decided about it. Nothing is lost by the ordering,
    # because neither turn may ask her anything, offer her anything or send a link, and the free
    # resource is withheld in `gate` on the flag rather than on the reason.
    if flags.get("stopped_trying"):
        return "stopped_trying"
    if flags.get("currently_pregnant") and not flags.get("wants_pregnancy_support"):
        # An announcement is a terminal conversation and nothing is offered into it. Round 5 left
        # the link open through one and the reply quoted the price range to a frightened woman who
        # had just shared her news.
        #
        # The exception is §D: she is pregnant and has asked for support through it, which is
        # The Pregnancy Solution and is a thing Sonia sells. That is a different conversation from
        # the announcement that usually precedes it, and the reader only sets the flag when she has
        # actually asked, so congratulating her stays the whole of the reply until she does.
        return "currently_pregnant"
    if slots.get("pregnancy_priority") == "low" and not _pregnancy_prospect(state):
        return "not_a_priority"

    # 2B.1 §15: enough of her situation has to be understood before an invitation is honest.
    # Two facts is a first message, not an understanding, an invitation that early is the
    # "every message is a sales opportunity" failure the manual opens by ruling out.
    # §L: her private coaching can be in Spanish, while group coaching and the program materials
    # are in English. That is a deal breaker for some women and it has to reach her before she
    # commits, not after she has paid, so a Spanish conversation cannot reach the link until she
    # has said English materials are workable for her. `turn.md` tells the writer to put the
    # question; this is what makes the answer matter.
    #
    # Keyed on the language she is actually writing in. A woman writing in English is not asked to
    # confirm she can read English.
    if slots.get("language") == "es" and not flags.get("accepts_english_materials"):
        # Her no comes first, because the two reasons want opposite replies out of the writer. The
        # undisclosed branch says "tell her and ask"; asking a woman who has already answered is
        # the failure §L is written to prevent.
        if flags.get("declines_english_materials"):
            return "declines_english_materials"
        return "english_materials_undisclosed"

    # The context count is about trying to conceive. A pregnant woman asking for support has told
    # us what matters by asking (§D, 2B.2 §7).
    if _pregnancy_prospect(state):
        return ""

    known = sum(
        1 for key in ("age", "time_trying", "conceiving_mode", "ivf_history", "iui_history",
                      "pregnancy_priority", "partner_status", "goal_stated")
        if _stated(slots.get(key))
    ) + (1 if slots.get("diagnoses") else 0) + (1 if slots.get("already_tried") else 0)
    if known < 3:
        return "not_enough_context"

    # No paid-program step before the link. 2B.1 §11 and 2B.2 §7: price is answered when she asks,
    # never held over the invitation as a warning she has to acknowledge.
    return ""


def _first_exchange(state: dict) -> bool:
    return int((state.get("counters") or {}).get("turns", 0)) <= 1


def _after_link_reply(state: dict, read: dict, before: dict | None) -> str:
    """What a message sent after the booking link needs a reply for, "" for nothing (2B.2 §8).

    She is paused once she has the link, and the team has her. Booking itself is still the AI's:
    she says she booked, she gives the email she booked with, what she says about her partner
    attending changes, or she asks a question before she has booked (Part 1 §3: her question is
    never ignored). Each counts only when it is new, because the reader reads booking from the
    whole conversation and "ok" after "booked!" must not be asked for the email again. Anything
    else, "thanks" included, is left for the team.
    """
    slots = state.get("slots") or {}
    previous = (before or {}).get("slots") or {}
    if slots.get("attendance") != previous.get("attendance"):
        return "attendance"
    if state.get("phase") == POST_BOOKING:
        return ""
    if slots.get("email") and slots.get("email") != previous.get("email"):
        return "email"
    already_booked = ((before or {}).get("flags") or {}).get("says_booked")
    if (read.get("flags") or {}).get("says_booked") and not already_booked:
        return "booked"
    if read.get("explicit_question") and not already_booked:
        return "question"
    return ""


def gate(state: dict, read: dict, before: dict | None = None) -> Gate:
    """Decide what the WRITE prompt may contain this turn. `before` is the pre-merge dossier."""
    reason = _escalation_reason(state, read, before)
    if reason:
        return _handover(reason)

    flags = state.get("flags") or {}
    raised = read.get("flags") or {}

    if state.get("phase") in (LINK_SENT, POST_BOOKING):
        reply_for = _after_link_reply(state, read, before)
        if not reply_for:
            return Gate(silent=True, notes=["after the link: nothing to answer"])
        blocks = {"attendance", "pricing"}
        if (state.get("slots") or {}).get("email"):
            blocks.add("post_booking")
        return Gate(blocks=blocks, after_link=reply_for, notes=[f"after the link: {reply_for}"])

    blocks = {"pricing", "free_resource"}
    if raised.get("asked_about_results"):
        blocks.add("proof")

    # The turn she tells you she has stopped is the terminal one, and §A allows it no CTA. The
    # booking block is already shut below; this shuts the other one, because a masterclass offered
    # to a woman who has just said she is not trying any more is a consolation prize for a decision
    # she did not ask you to have an opinion about.
    #
    # This turn only. If she comes back three messages later and asks something, that is a question
    # and it gets an honest answer, free resource included. What stays shut for good is the link.
    if raised.get("stopped_trying"):
        blocks.discard("free_resource")

    # Same reasoning, days after a loss. `_booking_blocked` already shuts the link on `recent_loss`
    # and the brief tells the writer to offer nothing, but the masterclass was still rendered into
    # the prompt, which leaves a free resource sitting in front of a model told to be warm. A
    # course offered to a woman whose pregnancy ended on Saturday is a CTA wearing sympathy.
    if flags.get("recent_loss"):
        blocks.discard("free_resource")

    blocked_for = _booking_blocked(state, read)
    # Someone who opens with "how do I work with you" is ready and should not be re-qualified;
    # everyone else gets at least one real exchange before a call is mentioned. A woman who says
    # "take my money" and tells you nothing about herself is still held by the `known < 3` check:
    # readiness to buy is not the same as being understood well enough to invite honestly.
    ready = read.get("intent") == "warm_prospect" or raised.get("wants_to_buy")
    if _first_exchange(state) and not ready and not blocked_for:
        blocked_for = "first_exchange"

    # §B: at 48 or over a person looks at it before the link goes out. The conversation carries on
    # until she is moving toward a call, and that turn is the review, never a rejection. Once the
    # team has released her the link opens as it would for anyone.
    age = (state.get("slots") or {}).get("age")
    if (not blocked_for and isinstance(age, int) and age >= AGE_REVIEW
            and not _pregnancy_prospect(state) and not flags.get("age_reviewed")):
        if ready:
            return _handover("age_review")
        blocked_for = "age_review_pending"

    if blocked_for:
        return Gate(blocks=blocks, notes=[f"no link: {blocked_for}"], block_reason=blocked_for)

    blocks |= {"booking", "attendance"}
    return Gate(allow_booking=True, blocks=blocks, notes=["link available"])


def _handover(reason: str) -> Gate:
    message = handover_message(reason)
    return Gate(
        escalate=True,
        escalate_reason=reason,
        handover_message=message,
        notes=[f"handover: {reason}" + (f", fixed line {message}" if message else ", silent")],
    )


def render(state: dict) -> str:
    """The dossier as the writer sees it."""
    slots = state.get("slots") or {}
    flags = state.get("flags") or {}

    lines = []
    for key, label in SLOT_LABELS.items():
        value = slots.get(key)
        if not value:
            continue
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        lines.append(f"- {label}: {value}")

    if flags.get("structural") and flags["structural"] not in ("none",):
        lines.append(f"- Structural finding she has mentioned: {flags['structural']}")
    if flags.get("wants_natural_only"):
        lines.append("- She wants natural conception and is not open to IVF")
    if flags.get("open_to_ivf"):
        lines.append("- She is open to IVF")

    if not lines:
        return (
            "# WHAT SHE HAS ALREADY TOLD ME\n\n"
            "Nothing yet. This is the start of the conversation."
        )

    return (
        "# WHAT SHE HAS ALREADY TOLD ME\n\n"
        "Never ask for any of this again. Build on it.\n\n" + "\n".join(lines)
    )
