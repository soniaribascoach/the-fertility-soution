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
    "miscarriage_history", "partner_status", "pregnancy_priority", "email", "goal_stated",
)
LIST_SLOTS = ("diagnoses", "already_tried", "testing_done")

# Any one of these hands the conversation to a person (2B.1 §10, 2B.2 §13). Order is priority:
# the first match names the reason, so the two safety flags come first.
#
# `needs_human` is the general one and the only one that needs to grow. The rest of the 2B.1 §10
# list (crisis, minors, a third party asking, medically complex history, contradictions, a
# conversation that has stopped moving) lives in `prompts/70_read.md` as prose rather than here as
# flag names, so adding a route is an edit to a prompt and not a deploy.
#
# The flags that carry a fixed line come before `needs_human`, because a woman who asked to speak
# to a person and also tripped the general flag should still be told a person is coming.
ESCALATION_FLAGS = (
    "crisis", "urgent_medical", "abusive", "asked_for_human", "asked_if_ai", "needs_human",
    "requested_medication", "requested_surgery_advice", "is_existing_client", "is_former_client",
)
ESCALATION_INTENTS = ("complaint", "collaboration", "media_request", "spam_or_aggression")

# A handover turn never calls the writer, so nothing about it is generated. Most handovers send
# nothing at all. These send one fixed line from config first, because silence is its own harm:
# a woman in crisis must not be met with an unanswered message, someone bleeding needs to be told
# to be seen today whether or not a human is awake, and total silence in answer to "is this a bot?"
# is the loudest possible yes.
HANDOVER_MESSAGES = {
    "crisis": "handover_message_crisis",
    "urgent_medical": "handover_message_urgent_medical",
    "asked_for_human": "handover_message_team",
    "asked_if_ai": "handover_message_team",
}

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
    tags: list = field(default_factory=list)   # extra selection tags this turn's facts imply

    @property
    def silent(self) -> bool:
        """A handover that sends nothing at all."""
        return self.escalate and not self.handover_message


# Boundary conversations are pulled by the fact that triggered the gate, not by whatever emotional
# tag the reader happened to pick. Someone of 38 who is frightened of running out of time must not
# be shown the conversation written for someone of 51.
_REASON_TAGS = {
    "age_over_48": "age_limit",
    "structural_menopause": "age_limit",
    "structural_no_uterus": "no_uterus",
    "tubal_status_unclear": "tubal",
    "both_tubes_without_ivf": "tubal",
    "demands_guarantee": "guarantee",
    "out_of_scope_request": "out_of_scope",
    "lab_request": "lab_request",
    "recent_loss": "loss_recent",
    "not_a_priority": "not_priority",
    "refuses_paid_coaching": "affordability",
    "currently_pregnant": "celebration",
}


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

    `30_operations.md` and `60_contract.md` both say to stop teaching and send the masterclass by
    the third one. Both have been in the prompt for five rounds and the spiral still runs to eight,
    because a rule about counting is being asked of a model that is not counting: it sees a
    reasonable question and answers it, and every answer is individually defensible.

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


def _escalation_reason(state: dict, read: dict) -> str:
    """Why this turn goes to a person. Empty string means it does not."""
    flags = state.get("flags") or {}
    slots = state.get("slots") or {}

    for flag in ESCALATION_FLAGS:
        # An unsupported language names itself rather than disappearing into the general flag,
        # because the person picking the conversation up needs to know they will need Portuguese.
        if flag == "needs_human" and slots.get("language") == "other":
            return "language_not_supported"
        if flags.get(flag):
            return flag

    if read.get("intent") in ESCALATION_INTENTS:
        return read["intent"]

    if slots.get("language") == "other":
        return "language_not_supported"

    if flags.get("structural") == "unclear_menopause":
        return "menopause_unclear"

    age = slots.get("age")
    if isinstance(age, int) and 46 <= age <= 48:
        return "age_needs_review"

    return ""


def _booking_blocked(state: dict, read: dict) -> str:
    """Why this turn may not offer the link. Empty string means it may."""
    flags = state.get("flags") or {}
    slots = state.get("slots") or {}
    structural = flags.get("structural")

    age = slots.get("age")
    if isinstance(age, int) and age > 48:
        return "age_over_48"
    if structural in BLOCKING_STRUCTURAL:
        return f"structural_{structural}"
    if structural == "unclear_tubal":
        return "tubal_status_unclear"
    if structural == "both_tubes" and (flags.get("wants_natural_only") or not flags.get("open_to_ivf")):
        return "both_tubes_without_ivf"
    if flags.get("refuses_paid_coaching"):
        return "refuses_paid_coaching"
    if flags.get("demands_guarantee"):
        return "demands_guarantee"
    # Read from this turn rather than from the dossier, and deliberately not sticky. "I'm planning
    # IVF in a month or two" is the sentence half of her audience opens with, and one reader misfire
    # on it used to shut the link for the whole conversation: every later turn was told to say what
    # she does not provide, so four messages were answered with four refusals and no question. What
    # she asked for on the turn she asked for it is still declined; what she asks next is a new
    # question.
    if (read.get("flags") or {}).get("wants_unprovided_service"):
        return "out_of_scope_request"
    if flags.get("requested_lab_interpretation"):
        # Refusing to read her results and inviting her to a call in the same breath turns the
        # boundary into a sales lever, which is exactly what Appendix A warns against.
        return "lab_request"
    if flags.get("recent_loss"):
        return "recent_loss"
    if flags.get("currently_pregnant"):
        # A live pregnancy is out of scope (2B.1 §2). Round 5 left the link open through a
        # pregnancy announcement, and the reply that followed quoted the price range to a
        # frightened woman who had just been told coaching through a pregnancy is not what this is.
        return "currently_pregnant"
    if slots.get("pregnancy_priority") == "low":
        return "not_a_priority"

    # Age is the one fact that can end the conversation by itself: 2B.1 §9 makes over 48 a hard
    # boundary and 2B.1 §10 sends 46 to 48 to a person. Both of those are checked above, and both
    # can only fire when she has actually given a number, so without this the boundary the manual
    # states most plainly was the one nothing ever enforced. A woman who never mentions her age
    # cleared the gate on the strength of three other slots and was sent the link.
    #
    # So it is a precondition rather than one of the eight below. The others can be worked out well
    # enough from the shape of her story for an invitation to still be honest without them. Age
    # cannot be worked out from anything, which is why `70_read.md` forbids the reader from
    # estimating one, and a blank left by that rule must not read here as a pass.
    if not _stated(slots.get("age")):
        return "age_unknown"

    # 2B.1 §15: enough of her situation has to be understood before an invitation is honest.
    # Two facts is a first message, not an understanding, an invitation that early is the
    # "every message is a sales opportunity" failure the manual opens by ruling out.
    known = sum(
        1 for key in ("age", "time_trying", "conceiving_mode", "ivf_history", "iui_history",
                      "pregnancy_priority", "partner_status", "goal_stated")
        if _stated(slots.get(key))
    ) + (1 if slots.get("diagnoses") else 0) + (1 if slots.get("already_tried") else 0)
    if known < 3:
        return "not_enough_context"

    return ""


# Step 4 of the conversation flow (Part 1 §8): the things the AI is supposed to check it knows
# before deciding anything, in the order they are worth asking for.
#
# The order is not a preference, it is what each answer can do to the conversation. Age can end it:
# past 48 there is no version of this she can be sold, so it is asked first and `_booking_blocked`
# will not let a link past without it. How long she has been trying and what she is doing about it
# shape the whole reply. Whether a baby is one of her biggest priorities is a pre-booking condition
# under 2B.1 §15. Partner status is last on purpose: it changes only who is invited to the call,
# so it is worth a question late and worth nothing early, and asking it first is how a conversation
# spends its one question on the fact that mattered least.
#
# The labels are what the writer is told is missing, so they are phrased as the thing to find out
# rather than as a field name.
DISCOVERY = (
    ("age", "how old she is"),
    ("time_trying", "how long she has been trying"),
    ("conceiving_mode", "whether she is trying naturally or preparing for IUI or IVF"),
    ("pregnancy_priority", "whether having a baby is one of her biggest priorities right now"),
    ("partner_status", "whether she is doing this with a partner or on her own"),
)


def missing_facts(state: dict) -> list[str]:
    """What Step 4 would still have her ask about, most useful first.

    The gate can withhold a link but it cannot ask a question, and for five rounds nothing told the
    writer why the link was missing or what would change it. A conversation was recorded where a
    frightened woman said yes to being helped four times, was never asked her age, and was
    eventually told a person would be in touch, which was not true.
    """
    slots = state.get("slots") or {}
    return [label for key, label in DISCOVERY if not _stated(slots.get(key))]


def _first_exchange(state: dict) -> bool:
    return int((state.get("counters") or {}).get("turns", 0)) <= 1


def gate(state: dict, read: dict) -> Gate:
    """Decide what the WRITE prompt may contain this turn."""
    reason = _escalation_reason(state, read)
    if reason:
        message = HANDOVER_MESSAGES.get(reason, "")
        return Gate(
            allow_booking=False,
            escalate=True,
            escalate_reason=reason,
            handover_message=message,
            blocks=set(),
            notes=[f"handover: {reason}" + (f", fixed line {message}" if message else ", silent")],
        )

    blocks = {"pricing", "free_resource"}
    extra_tags = []
    if state.get("phase") in (LINK_SENT, POST_BOOKING):
        blocks.add("post_booking")
        extra_tags.append("post_booking")

    blocked_for = _booking_blocked(state, read)
    # Someone who opens with "how do I work with you" is ready and should not be re-qualified;
    # everyone else gets at least one real exchange before a call is mentioned.
    if not blocked_for and _first_exchange(state) and read.get("intent") != "warm_prospect":
        blocked_for = "first_exchange"

    if blocked_for:
        tag = _REASON_TAGS.get(blocked_for)
        return Gate(
            allow_booking=False,
            blocks=blocks,
            notes=[f"no link: {blocked_for}"],
            block_reason=blocked_for,
            tags=extra_tags + ([tag] if tag else []),
        )

    blocks.add("booking")
    return Gate(allow_booking=True, blocks=blocks, notes=["link available"], tags=extra_tags)


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
    if flags.get("understands_coach_not_clinic"):
        lines.append("- She already understands I am a coach and not a clinic. Do not re-explain it")
    if flags.get("understands_paid_program"):
        lines.append("- She already knows this is a paid program. Do not re-announce it")
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
