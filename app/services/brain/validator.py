"""Output Validator — the last deterministic gate before anything is sent.

It is action-aware. Scripted actions must match their registry template
verbatim (so a bug in the orchestrator can never silently mutate approved
text). The one composed action (ASK_DISCOVERY) is checked against the hard
rules: no links, no medical advice, no invented prices, no markdown/em-dashes,
exactly one question, and a short length.

Research on guardrails shows combining structural + regex checks catches the
overwhelming majority of bad outputs; this layer is that net.
"""
import re
from dataclasses import dataclass, field

from app.services.brain.constants import Action
from app.services.brain import scripts

_URL_RE = re.compile(r"https?://\S+")
_MD_RE = re.compile(r"(\*\*|##|__|^\s*[-*•]\s)", re.M)
_MONEY_RE = re.compile(r"\$\s*\d")
# Dosage language that would constitute medical advice. NOTE: "prescribe" and
# "protocol" are deliberately excluded — they appear in Sonia's own disclaimer
# ("I don't prescribe medication"), so flagging them causes false positives. The
# GEval "no medical advice" judge is the semantic backstop for real advice.
_MEDICAL_RE = re.compile(
    r"\b\d+\s?(mg|mcg|iu)\b|\bmilligram|\bdosage\b",
    re.I,
)
_EMDASH = "—"


@dataclass
class ValidationResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


def validate(action: Action, text: str, cfg: dict | None = None) -> ValidationResult:
    """Validate an outgoing message for the given action."""
    if action != Action.ASK_DISCOVERY:
        # Scripted action: the only requirement is verbatim fidelity.
        try:
            expected = scripts.render(action, cfg)
        except KeyError:
            return ValidationResult(False, ["no_template"])
        if text.strip() != expected.strip():
            return ValidationResult(False, ["not_verbatim"])
        return ValidationResult(True, [])

    # Composed discovery reply: enforce the hard rules.
    violations: list[str] = []
    if not text.strip():
        violations.append("empty")
    if _URL_RE.search(text):
        violations.append("url")
    if _MONEY_RE.search(text):
        violations.append("money")
    if _MEDICAL_RE.search(text):
        violations.append("medical_advice")
    if _EMDASH in text:
        violations.append("em_dash")
    if _MD_RE.search(text):
        violations.append("markdown")
    q = text.count("?")
    if q != 1:
        violations.append(f"question_count={q}")
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if len(sentences) > 4 or len(text) > 500:
        violations.append("too_long")
    return ValidationResult(len(violations) == 0, violations)


_URL_FIND = re.compile(r"https?://[^\s)]+")


def validate_generated(directive, text: str) -> ValidationResult:
    """Validate a Voice-generated message against its TurnDirective.

    This is the safety net that makes generation safe: it enforces the same hard
    rules the verbatim scripts guaranteed (no link/price out of context, no
    medical advice, required disclaimer/URL/figure present, bounded length).
    """
    v: list[str] = []
    t = text or ""
    if not t.strip():
        return ValidationResult(False, ["empty"])

    # Any URL present must be explicitly allowed this turn.
    for u in _URL_FIND.findall(t):
        u_clean = u.rstrip(".,!?")
        if not any(a and (a in u_clean or u_clean in a) for a in directive.allow_urls):
            v.append("disallowed_url")
            break

    # Required substrings (booking/masterclass URL, closer phone, price figure).
    for token in directive.must_include:
        if token not in t:
            v.append(f"missing:{token[:20]}")

    # The not-a-doctor disclaimer, when required (pinned_text on a generate turn).
    if directive.generate and directive.pinned_text and directive.pinned_text.lower() not in t.lower():
        v.append("missing_disclaimer")

    # Price figure only when the reveal is allowed.
    if not directive.allow_price_figure and _MONEY_RE.search(t):
        v.append("unexpected_price")

    if _MEDICAL_RE.search(t):
        v.append("medical_advice")
    if _EMDASH in t:
        v.append("em_dash")
    if _MD_RE.search(t):
        v.append("markdown")
    if t.count("?") > 1:
        v.append("too_many_questions")
    if len(t) > directive.max_chars:
        v.append("too_long")

    return ValidationResult(len(v) == 0, v)
