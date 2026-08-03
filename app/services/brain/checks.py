"""Output checks. Everything here is code except `checker.py`'s LLM pass.

Three layers, cheapest first:

* `validate_draft` - hard rules. URLs, price, medical language, format, and the
  per-mode question policy. A CELEBRATE reply containing a question is rejected
  here, which is how "not every message ends with a question" becomes a
  guarantee rather than an instruction.
* `ground` - every fact about the lead must trace to something she said, and
  every claim about fertility or Sonia's approach must trace to a retrieved
  knowledge entry. Free, and it is what makes answering real questions safe.
* `no_repeat` - a sentence close to one already sent in this conversation is
  rejected. This is what stops the identical discovery question Sonia quoted.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from app.services.brain.constants import ResponseMode
from app.services.brain.writer import (
    AT_MOST_ONE, FORBIDDEN, OPTIONAL, REQUIRED, MODE_SPECS,
)


# Violations that make a reply UNSAFE rather than merely clumsy. Only these are
# worth going silent over: sending nothing has a real cost to the lead, so a
# repeated question or an em-dash must not silence a turn the way a leaked link
# or invented lab value should.
HARD_VIOLATIONS = (
    "disallowed_url", "missing_required_url", "unexpected_price", "medical_advice",
    "question_not_allowed", "invented_number", "invented_email", "echoed_lead",
    "empty",
)


def is_hard(violation: str) -> bool:
    name = violation.split(":")[0]
    return name in HARD_VIOLATIONS


@dataclass
class CheckResult:
    ok: bool
    violations: list = field(default_factory=list)

    @property
    def hard(self) -> list:
        """The violations that justify saying nothing at all."""
        return [v for v in self.violations if is_hard(v)]


_URL_RE = re.compile(r"https?://[^\s)]+")
_MD_RE = re.compile(r"(\*\*|##|__|^\s*[-*•]\s)", re.MULTILINE)
_PRICE_RE = re.compile(r"\$\s*\d")
# Dosage-shaped language only. "prescribe"/"protocol" are deliberately absent:
# they appear in Sonia's own not-a-doctor disclaimer. The LLM checker is the
# semantic backstop for the rest.
_MEDICAL_RE = re.compile(
    # A number with a unit is the thing that must never appear. The bare words
    # are also blocked, but note the plurals: `\bdosage\b` silently missed
    # "dosages", which is how the more natural phrasing slipped through.
    r"\b\d+\s?(mg|mcg|iu|ui)\b|\bmilligrams?\b|\bdosages?\b|\bdoses\b"
    r"|\bdosis\b|dosificaci[oó]n|\bmiligramos?\b|\bmicrogramos?\b",
    re.IGNORECASE,
)

# Tiny regression backstop only. Tone is fixed in the writer prompt and the
# few-shots; this list exists to catch a specific relapse, not to shape voice.
# Appendix A of the Operating Manual, "Responses Sonia Would Never Send". This is
# HER enumerated list, not a list of phrases we guessed at, which is the only
# reason it is a list at all: tone is otherwise a job for the prompt and the
# retrieved examples, never for a regex. Soft violation - it forces a rewrite,
# never silence.
_BANNED = [
    # A.1 generic empathy
    "thank you for sharing", "thanks for sharing", "i appreciate you sharing",
    "i appreciate your honesty", "i'm glad to hear", "im glad to hear",
    "that's great to hear", "it's wonderful to hear", "i admire",
    "i hear you", "i get that", "i completely understand", "i totally get it",
    "you're not alone", "youre not alone", "that must be so difficult",
    "i'm so sorry you're going through this", "im so sorry youre going through this",
    # A.2 generic AI language
    "everyone's journey is different", "everyones journey is different",
    "every body is unique", "your body knows what to do",
    "healing isn't linear", "healing isnt linear", "trust the process",
    "everything happens for a reason", "your body just needs to feel safe",
    # A.3 overused marketing language
    "holistic approach", "whole-body approach", "whole body approach",
    "root cause", "optimize your biology", "optimise your biology",
    "transform your fertility", "empower your fertility",
    # A.4 empty encouragement
    "you've got this", "youve got this", "don't give up", "dont give up",
    "stay positive", "keep believing", "everything will work out",
    # A.10 false hope
    "i can fix this", "you will get pregnant", "i know this will help",
    # Spanish equivalents already reported by the client
    "gracias por compartir", "te agradezco", "aprecio tu honestidad",
    "me alegra saber", "que bueno escuchar", "admiro",
]


def _fold(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip().casefold()


# Sonia addresses every lead informally. The voice prompt says so, but nothing
# enforced it: the only guard was a GEval judge, which flaked in both directions
# for three sessions before it was replaced by this line. `usted` is the giveaway
# and it is exact, free, and cannot drift between runs.
_USTED_RE = re.compile(r"\busted(es)?\b", re.IGNORECASE)


def validate_draft(
    bubbles: list[str],
    *,
    mode: ResponseMode,
    allow_urls: list,
    allow_price: bool = False,
    language: str = "en",
) -> CheckResult:
    spec = MODE_SPECS[mode]
    text = " ".join(bubbles).strip()
    v: list[str] = []

    if not text:
        return CheckResult(False, ["empty"])

    for url in _URL_RE.findall(text):
        cleaned = url.rstrip(".,!?)")
        if not any(cleaned in allowed or allowed in cleaned for allowed in allow_urls):
            v.append("disallowed_url")
            break
    if spec.require_url and allow_urls:
        if not any(u in text for u in allow_urls):
            v.append("missing_required_url")

    if not allow_price and _PRICE_RE.search(text):
        v.append("unexpected_price")
    if language == "es" and _USTED_RE.search(text):
        v.append("formal_address")

    if _MEDICAL_RE.search(text):
        v.append("medical_advice")

    # Question policy, enforced in BOTH directions. The old validator only
    # capped at one and never permitted zero, so every reply ended in a question.
    q = text.count("?")
    if spec.question_policy == FORBIDDEN and q > 0:
        v.append("question_not_allowed")
    elif spec.question_policy == REQUIRED and q != 1:
        v.append("expected_exactly_one_question")
    elif spec.question_policy in (AT_MOST_ONE, OPTIONAL) and q > 1:
        # OPTIONAL means "one question or none", never a pile of them. Without
        # this cap an ANSWER turn could stack three, which is an interrogation.
        v.append("too_many_questions")

    if "—" in text:
        v.append("em_dash")
    if _MD_RE.search(text):
        v.append("markdown")

    folded = _fold(text)
    for phrase in _BANNED:
        if _fold(phrase) in folded:
            v.append(f"banned_phrase:{phrase}")
            break

    if len(bubbles) > spec.bubbles[1]:
        v.append("too_many_bubbles")
    if len(text) > spec.max_chars:
        v.append("too_long")

    return CheckResult(not v, v)


# --- Grounding ----------------------------------------------------------------

# Shapes that assert something concrete. If one of these appears in the reply it
# has to be traceable to her words or to approved substance.
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def ground(
    bubbles: list[str],
    *,
    lead_texts: list[str],
    knowledge_texts: list[str],
    known_facts: dict,
) -> CheckResult:
    """Reject numbers and emails the reply invented.

    Deliberately narrow. Numbers, ages, durations and emails are where a
    fabricated detail does real damage ("you said your AMH was fine, right?").
    Free-text claims about fertility are the LLM checker's job - a regex cannot
    judge those, and pretending otherwise would give false confidence.
    """
    text = " ".join(bubbles)
    haystack = _fold(" ".join(lead_texts) + " " + " ".join(knowledge_texts) + " "
                     + " ".join(str(v) for v in known_facts.values()))
    v = []

    for email in _EMAIL_RE.findall(text):
        if _fold(email) not in haystack:
            v.append("invented_email")
            break

    for number in _NUMBER_RE.findall(text):
        # Small WHOLE numbers are scale references and ordinary counts ("1 to 10",
        # "2 rounds"); policing them is noise. Decimals are not: an AMH of 0.6 is
        # a lab value, and inventing one is exactly the damage this check exists
        # to prevent, so a decimal is always checked however small.
        if "." not in number and float(number) <= 10:
            continue
        if number not in haystack:
            v.append(f"invented_number:{number}")
            break

    return CheckResult(not v, v)


# --- No repeats ---------------------------------------------------------------

def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if len(s.strip()) > 12]


_WORD_RE = re.compile(r"[a-z0-9']+")


def _words(text: str) -> set:
    """Bare word tokens. Punctuation is stripped so "link." and "link" match -
    without this, one trailing full stop was enough to hide an exact echo."""
    return set(_WORD_RE.findall(_fold(text)))


def _similar(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def no_repeat(bubbles: list[str], history: list[dict], *, threshold: float = 0.7) -> CheckResult:
    """Reject a sentence that closely matches one Sonia already sent.

    Sonia: 'We repeatedly saw phrases such as ... used across very different
    conversations.' Within one conversation the old brain could not avoid this,
    because the reference text handed to the model WAS the same sentence.
    """
    said = []
    for m in history:
        if m.get("role") == "assistant":
            said.extend(_sentences(m.get("content", "")))
    for sentence in _sentences(" ".join(bubbles)):
        for previous in said:
            if _similar(sentence, previous) >= threshold:
                return CheckResult(False, [f"repeat:{sentence[:40]}"])
    return CheckResult(True, [])


def no_stock_opening(
    bubbles: list[str],
    recent_openings: list[str],
    *,
    threshold: float = 0.8,
) -> CheckResult:
    """Reject an opening line already used on OTHER leads.

    `no_repeat` only sees one conversation, but Sonia's complaint was explicitly
    cross-conversation: "We repeatedly saw phrases such as 'I hear you' ... used
    across very different conversations and objections, making the replies feel
    automated." Within a single thread the bot looked fine; the sameness was only
    visible to the person reading all of them.

    Only the FIRST sentence is compared. Two replies can legitimately share a
    later sentence - an approved boundary, a link instruction - but a shared
    opening is what makes a set of conversations read as one template. Soft on
    purpose: rephrasing is worth a regeneration, never silence.

    `recent_openings` is passed in rather than queried so this module stays pure.
    """
    if not recent_openings:
        return CheckResult(True, [])
    opening = next(iter(_sentences(" ".join(bubbles))), "")
    if not opening:
        return CheckResult(True, [])
    for previous in recent_openings:
        if _similar(opening, previous) >= threshold:
            return CheckResult(False, [f"stock_opening:{opening[:40]}"])
    return CheckResult(True, [])


def no_echo(bubbles: list[str], lead_texts: list[str], *, threshold: float = 0.75) -> CheckResult:
    """Reject a reply that parrots the lead's own message back at her.

    Seen live: a "just send me the booking link" turn came back as
    "just send me the booking link. I can feel how much you want this." The
    transcript sits in the writer's prompt, and a small model will sometimes
    continue it instead of replying to it. Nothing else catches this and it
    reads as broken.
    """
    for text in lead_texts:
        if len(_fold(text)) < 12:
            continue
        for bubble in bubbles:
            if _similar(bubble, text) >= threshold:
                return CheckResult(False, [f"echoed_lead:{bubble[:40]}"])
            # Also catch the opening-clause case, where her sentence is used as
            # a preamble before the real reply.
            first = _sentences(bubble)[:1]
            if first and _similar(first[0], text) >= threshold:
                return CheckResult(False, [f"echoed_lead_opening:{first[0][:40]}"])
    return CheckResult(True, [])


def no_reask(bubbles: list[str], known_facts: dict) -> CheckResult:
    """Reject a question about something she already told us.

    Best-effort by design: this matches a question sentence against keywords for
    a known slot. The real protection is that committed facts sit in the writer's
    prompt in her own words; this catches the blatant relapse.
    """
    keywords = {
        "age": ["how old", "your age", "cuantos anos"],
        "trying_duration": ["how long have you been trying", "how long you", "cuanto tiempo"],
        "what_tried": ["what have you tried", "what else have you", "que has probado"],
        "done_testing": ["done any testing", "had any testing", "fertility testing"],
        "partner_status": ["do you have a partner", "are you doing this with"],
        "priority_score": ["scale of 1 to 10", "scale of one to ten"],
    }
    text = _fold(" ".join(bubbles))
    for slot, phrases in keywords.items():
        if known_facts.get(slot) in (None, "", False):
            continue
        if any(_fold(p) in text for p in phrases):
            return CheckResult(False, [f"reask:{slot}"])
    return CheckResult(True, [])


def run_all(
    bubbles: list[str],
    *,
    mode: ResponseMode,
    allow_urls: list,
    allow_price: bool,
    history: list[dict],
    lead_texts: list[str],
    knowledge_texts: list[str],
    known_facts: dict,
    recent_openings: Optional[list[str]] = None,
    language: str = "en",
) -> CheckResult:
    """Every code-level check, combined. No LLM, so this runs on every turn."""
    violations = []
    for result in (
        validate_draft(bubbles, mode=mode, allow_urls=allow_urls,
                       allow_price=allow_price, language=language),
        ground(bubbles, lead_texts=lead_texts, knowledge_texts=knowledge_texts,
               known_facts=known_facts),
        no_repeat(bubbles, history),
        no_stock_opening(bubbles, recent_openings or []),
        no_echo(bubbles, lead_texts),
        no_reask(bubbles, known_facts),
    ):
        violations.extend(result.violations)
    return CheckResult(not violations, violations)
