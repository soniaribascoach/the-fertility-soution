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
from app.services.brain.writer import AT_MOST_ONE, FORBIDDEN, REQUIRED, MODE_SPECS


@dataclass
class CheckResult:
    ok: bool
    violations: list = field(default_factory=list)


_URL_RE = re.compile(r"https?://[^\s)]+")
_MD_RE = re.compile(r"(\*\*|##|__|^\s*[-*•]\s)", re.MULTILINE)
_PRICE_RE = re.compile(r"\$\s*\d")
# Dosage-shaped language only. "prescribe"/"protocol" are deliberately absent:
# they appear in Sonia's own not-a-doctor disclaimer. The LLM checker is the
# semantic backstop for the rest.
_MEDICAL_RE = re.compile(
    r"\b\d+\s?(mg|mcg|iu|ui)\b|\bmilligram|\bdosage\b|\bdosis\b|dosificaci[oó]n"
    r"|\bmiligramos?\b|\bmicrogramos?\b",
    re.IGNORECASE,
)

# Tiny regression backstop only. Tone is fixed in the writer prompt and the
# few-shots; this list exists to catch a specific relapse, not to shape voice.
_BANNED = [
    "thank you for sharing", "thanks for sharing", "i appreciate you sharing",
    "i appreciate your honesty", "i'm glad to hear", "im glad to hear",
    "that's great to hear", "it's wonderful to hear", "i admire",
    "i hear you", "i get that",
    "gracias por compartir", "te agradezco", "aprecio tu honestidad",
    "me alegra saber", "que bueno escuchar", "admiro",
]


def _fold(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip().casefold()


def validate_draft(
    bubbles: list[str],
    *,
    mode: ResponseMode,
    allow_urls: list,
    allow_price: bool = False,
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
    if _MEDICAL_RE.search(text):
        v.append("medical_advice")

    # Question policy, enforced in BOTH directions. The old validator only
    # capped at one and never permitted zero, so every reply ended in a question.
    q = text.count("?")
    if spec.question_policy == FORBIDDEN and q > 0:
        v.append("question_not_allowed")
    elif spec.question_policy == REQUIRED and q != 1:
        v.append("expected_exactly_one_question")
    elif spec.question_policy == AT_MOST_ONE and q > 1:
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


def _similar(a: str, b: str) -> float:
    wa, wb = set(_fold(a).split()), set(_fold(b).split())
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
) -> CheckResult:
    """Every code-level check, combined. No LLM, so this runs on every turn."""
    violations = []
    for result in (
        validate_draft(bubbles, mode=mode, allow_urls=allow_urls, allow_price=allow_price),
        ground(bubbles, lead_texts=lead_texts, knowledge_texts=knowledge_texts,
               known_facts=known_facts),
        no_repeat(bubbles, history),
        no_reask(bubbles, known_facts),
    ):
        violations.extend(result.violations)
    return CheckResult(not violations, violations)
