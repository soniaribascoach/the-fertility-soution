"""Reading a bare answer against the question we actually asked. Pure code, NO LLM.

The live AMH transcript died here. Sonia asked "would you be open to my paid
programme?", the lead said "yes", and `financial_ready` stayed null - so the same
question came back on the next turn, and the next, and the next. Four "yes"es,
four re-asks, no booking link.

The classifier cannot be the thing that fixes it. It is told to resolve a short
message against Sonia's previous turn, but the writer rephrases every question
("is this the kind of support you're looking for" became "would you be open to
discussing how my program can support you"), so by the time the model reads the
transcript there is no fixed sentence left to match against. What IS fixed is the
question key the brain chose - it is in the lead state. So a bare answer is
resolved here, in code, against that key, and the model's reading is a bonus
rather than the mechanism.

`QUESTIONS` is the single source for both halves: the key the state remembers and
the topic the writer is handed. They cannot drift apart.
"""
import re
from typing import Optional

# key -> the topic handed to the writer. The writer phrases it itself; handing
# over an approved sentence is what made every discovery message identical.
QUESTIONS: dict[str, str] = {
    "trying_duration": "how long she has been trying, and what she has already tried",
    "age": "her age",
    "treatment_path": "whether she is trying naturally, doing IUI or IVF, or still deciding",
    "done_testing": "whether she has had any fertility testing",
    "diagnosis": "whether a doctor has given her a diagnosis",
    "priority": "how much of a priority getting pregnant is for her right now",
    "role": "whether this is the kind of support she is looking for",
    "financial": "whether she is open to this being a paid programme, if it feels right",
    "partner": "whether she is doing this with a partner or on her own",
    "partner_join": "whether her partner could join the call",
}

# Phrases that prove a question of this key has already been put to her, so the
# writer can be told to reword rather than repeat itself into a rejected draft.
ASKED_MARKERS: dict[str, tuple] = {
    "trying_duration": ("how long have you been trying", "how long you have been trying",
                        "cuanto tiempo llevan intentando"),
    "age": ("how old are you", "cuantos anos tienes"),
    "treatment_path": ("trying naturally", "iui", "still deciding"),
    "done_testing": ("fertility testing", "any testing"),
    "diagnosis": ("diagnosis",),
    "priority": ("scale of 1 to 10", "top priority", "priority"),
    "role": ("kind of support", "looking for"),
    "financial": ("paid program", "paid coaching", "paid programme"),
    "partner": ("with a partner", "on your own"),
    "partner_join": ("join the call",),
}

# Which slot a yes/no answer to that question settles. Only genuinely binary
# questions appear here: "are you doing this with a partner or on your own" is
# not one, so it is deliberately absent.
YES_NO_SLOT: dict[str, str] = {
    "role": "open_to_holistic",
    "financial": "financial_ready",
    "partner_join": "partner_can_join",
}

_AFFIRMATIVE = frozenset({
    "yes", "yeah", "yep", "yup", "yes please", "yes i am", "yes i do", "yes it is",
    "sure", "ok", "okay", "of course", "absolutely", "definitely", "certainly",
    "totally", "for sure", "100%", "i am", "i do", "i would", "i would be",
    "sounds good", "that sounds good", "sounds great", "please do", "correct",
    "si", "sí", "claro", "claro que si", "por supuesto", "obvio", "dale",
    "me interesa", "si por favor",
})

_NEGATIVE = frozenset({
    "no", "nope", "nah", "not really", "no thanks", "no thank you", "not right now",
    "not at the moment", "not for now", "i cant", "i can't", "no i cant", "no i can't",
    "no puedo", "no gracias", "ahora no", "todavia no", "todavía no",
})

# A longer message may still open with an unmistakable yes ("yes definitely, that
# is exactly what I have been looking for"). Negatives get no such latitude: a
# wrong False silently blocks her forever, and "no idea what you mean" starts
# with one.
_AFFIRMATIVE_HEADS = ("yes", "yeah", "yep", "yup", "sure", "absolutely",
                      "definitely", "si", "sí", "claro")
_MAX_HEAD_CHARS = 60

_STRIP_RE = re.compile(r"[^\w%\s']+", re.UNICODE)
_WS_RE = re.compile(r"\s+")
# A rating she gave, said outright: "8", "a 9", "10/10", "I'd say 7".
_RATING_RE = re.compile(r"\b(10|[1-9])\s*(?:/|out of)\s*10\b")
_NUMBER_RE = re.compile(r"\b(10|[1-9])\b")

# Words that make a number something OTHER than a rating. "very high, i have
# been married for 5 years" was read as a priority of 5 out of 10, which put a
# committed lead below the gate and looped her into a human handoff. Any number
# carrying a unit, or introduced by one of these, is part of her story.
_NOT_A_RATING = re.compile(
    r"(?:\b(?:for|since|been|married|together|trying|ttc|past|last|nearly|almost|age|aged|im|i m)\s+"
    r"(?:10|[1-9])\b)"
    r"|(?:\b(?:10|[1-9])\s*(?:st|nd|rd|th)?\s*"
    r"(?:year|yr|month|mo|week|wk|day|kid|child|children|cycle|round|transfer|"
    r"embryo|egg|iui|ivf|attempt|time|hour|min|am|pm|k\b|%))"
)

# How much room a rating gets to sit in. She answers a 1-10 question with a
# number and maybe a few words; a number buried in a sentence about her life is
# not an answer to it.
_MAX_RATING_CHARS = 40

# "very high" is an answer to the priority question, not a 10. The classifier
# used to return priority_score=10 quoting "very high", which is an invented
# number; the manual counts an intensity answer as strong readiness instead.
_INTENSITY = (
    "very high", "really high", "extremely high", "super high", "highest",
    "high", "urgent", "asap", "as soon as possible", "top priority",
    "biggest priority", "number one", "most important", "so important",
    "really important", "very important", "everything to me", "my everything",
    "more than anything", "all i want", "all we want", "desperate",
    "muy alta", "altisima", "altísima", "urgente", "lo antes posible",
    "lo mas importante", "lo más importante", "mi prioridad",
)

# "not urgent", "it's less of a priority right now" - the same words with the
# meaning reversed. A missed answer costs one re-ask; a reversed one books her.
_NEGATED = re.compile(r"\b(not|isn t|aren t|don t|doesn t|wasn t|never|less|no)\b")


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", _STRIP_RE.sub(" ", (text or "").casefold())).strip()


def polarity(text: str) -> Optional[bool]:
    """True / False for an unmistakable yes or no; None for anything else."""
    norm = _norm(text)
    if not norm:
        return None
    if norm in _AFFIRMATIVE:
        return True
    if norm in _NEGATIVE:
        return False
    if "?" in (text or "") or " but " in f" {norm} ":
        return None
    head = norm.split(" ", 1)[0]
    if head in _AFFIRMATIVE_HEADS and len(norm) <= _MAX_HEAD_CHARS:
        return True
    return None


def _rating(norm: str) -> Optional[int]:
    """The 1-10 she gave, or None if the numbers in her message are her life.

    Order matters: "8/10, we've been trying 3 years" is a rating, and the years
    must not disqualify it.
    """
    explicit = _RATING_RE.search(norm)
    if explicit:
        return int(explicit.group(1))
    if len(norm) > _MAX_RATING_CHARS or _NOT_A_RATING.search(norm):
        return None
    match = _NUMBER_RE.search(norm)
    return int(match.group(1)) if match else None


def _priority_deltas(text: str) -> dict:
    norm = _norm(text)
    score = _rating(norm)
    if score is not None:
        return {"priority_score": score}
    # No number, but she answered the question all the same. The manual counts
    # this as a strong-priority signal in its own right.
    if any(phrase in norm for phrase in _INTENSITY) and not _NEGATED.search(norm):
        return {"strong_readiness": True}
    if polarity(text) is True:
        return {"strong_readiness": True}
    return {}


def resolve(pending: Optional[str], texts: list[str]) -> dict:
    """Slot values her answer settles, given the question the brain last asked.

    Empty dict whenever the answer is not plainly one thing or the other - an
    unresolved answer costs one re-ask, and a wrongly resolved one puts an
    unqualified lead on the calendar.
    """
    if not pending:
        return {}
    text = " ".join(t for t in texts if t).strip()
    if not text:
        return {}
    if pending == "priority":
        return _priority_deltas(text)
    slot = YES_NO_SLOT.get(pending)
    if not slot:
        return {}
    answer = polarity(text)
    return {} if answer is None else {slot: answer}
