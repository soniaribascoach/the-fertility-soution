"""One uncertainty score, one threshold.

Sonia asked that anything the bot is not sure about goes to a person. In the old
brain that intent was spread across six unrelated code paths - an LLM boolean, an
intent set, slot checks, a config phrase list, a loop guard, and a repeat counter -
so it could not be tuned or tested as one behaviour.

Here every doubt signal contributes to a single number, compared against one
`uncertainty_threshold` in app_config that ops can raise or lower without a
deploy. Ship it strict and loosen it with real data.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 3

# What each signal is worth. A single strong signal (an invented fact, a judge
# veto) is enough on its own; weaker ones have to accumulate.
WEIGHTS = {
    "intent_unsure": 5,
    "off_script": 5,
    "contradiction": 5,
    "checker_faithful": 5,        # the reply invented something
    "checker_answered": 2,        # it dodged her question
    "checker_premature": 5,       # it sold before the gate
    "checker_unavailable": 2,
    "grounding_failure": 5,
    "writer_unsure": 3,
    "hard_violation": 3,          # link/price/medical rule broken
    "regenerated": 1,             # needed a second attempt
    # Two attempts and the rules are still broken: the writer is stuck, so send
    # nothing. Without this a banned phrase or a second question survives both
    # passes and goes out anyway, which is the templated tone Sonia rejected.
    "failed_twice": 5,
    "soft_violation": 1,          # tone or format only
    # The model offered a quote and the quote is not in her message: it invented
    # her words. Distinct from an unevidenced inference, which is routine and
    # scores nothing - charging for those flagged every ordinary turn.
    "fabricated_quote": 3,
    "intent_probable": 1,
    "repeat_pressure": 2,
}

_HARD = ("disallowed_url", "unexpected_price", "medical_advice", "missing_required_url",
         "question_not_allowed")


@dataclass
class Uncertainty:
    score: int = 0
    signals: list = field(default_factory=list)

    def add(self, name: str, times: int = 1) -> None:
        weight = WEIGHTS.get(name, 1) * times
        if weight:
            self.score += weight
            self.signals.append(name if times == 1 else f"{name}x{times}")

    def over(self, threshold: int) -> bool:
        return self.score >= threshold


def threshold_from(cfg: Optional[dict]) -> int:
    raw = (cfg or {}).get("uncertainty_threshold")
    try:
        value = int(str(raw).strip())
        return value if value > 0 else DEFAULT_THRESHOLD
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD


def score_turn(
    *,
    intent_certainty: str,
    off_script: bool,
    fabricated_slots: list,
    contradictions: list,
    writer_unsure: bool,
    code_violations: list,
    checker_violations: list,
    regenerated: bool,
    still_failing: bool = False,
    repeat_count: int = 0,
) -> Uncertainty:
    u = Uncertainty()

    if intent_certainty == "unsure":
        u.add("intent_unsure")
    elif intent_certainty == "probable":
        u.add("intent_probable")

    if off_script:
        u.add("off_script")
    if fabricated_slots:
        u.add("fabricated_quote", len(fabricated_slots))
    if contradictions:
        u.add("contradiction")
    if writer_unsure:
        u.add("writer_unsure")
    if regenerated:
        u.add("regenerated")
    if still_failing:
        u.add("failed_twice")
    if repeat_count >= 2:
        u.add("repeat_pressure")

    for violation in code_violations:
        if violation.startswith("invented_"):
            u.add("grounding_failure")
        elif violation.split(":")[0] in _HARD:
            u.add("hard_violation")
        else:
            u.add("soft_violation")

    for violation in checker_violations:
        name = violation.split(":")[0]
        u.add(f"checker_{name}" if f"checker_{name}" in WEIGHTS else "soft_violation")

    return u


def should_check(
    *, intent_certainty: str, off_script: bool, writer_unsure: bool,
    code_violations: list, gate_just_opened: bool, question_asked: Optional[str],
) -> bool:
    """Whether the LLM veto panel is worth its call this turn.

    Deliberately broad on the turns that matter (a link going out, a question
    being answered) and quiet on routine ones.
    """
    return bool(
        gate_just_opened
        or question_asked
        or writer_unsure
        or off_script
        or code_violations
        or intent_certainty != "certain"
    )
