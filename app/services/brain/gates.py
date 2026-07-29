"""Qualification gates and out-of-scope checks. Pure functions, NO LLM, NO state mutation.

This is the single source of truth for "may this lead be sent the booking link" and
"is this lead out of scope". Extracted from `controller.py` so that every brain version
shares one implementation: forking the booking gate is the one refactoring mistake that
could put unqualified leads on the calendar.

Everything here is a predicate over `lead_state` (see `constants.empty_lead_state`).
The callers own the side effects — building a `Decision`, setting flags, pausing — so
these functions can be reused by a router that never touches the funnel at all.
"""
import re
from dataclasses import dataclass
from typing import Optional

from app.services.brain.constants import Action, Phase


# --- Qualification predicates ------------------------------------------------

def _actively_ttc(s: dict) -> bool:
    return bool(s.get("trying_duration") or s.get("what_tried") or s.get("treatment_path"))


def _priority_ok(s: dict) -> bool:
    score = s.get("priority_score")
    return (isinstance(score, int) and score >= 8) or s.get("strong_readiness") is True


def _partner_resolved(s: dict) -> bool:
    status = s.get("partner_status")
    if status in ("solo", "donor", "single_by_choice"):
        return True
    if status == "couple":
        # Resolved once we know whether he is coming, either way: if he is not,
        # she books with the couples expectation set rather than being quizzed
        # about who decides (Sonia v1.2 - the answer no longer gates the link, so
        # asking for it is friction). She alone deciding also resolves it.
        return (
            s.get("partner_can_join") is not None
            or s.get("partner_is_decision_maker") is False
        )
    return False


def _shares_decision_but_absent(s: dict) -> bool:
    """A partner who will not attend is ASSUMED to share the decision unless she
    has told us otherwise. We never ask: both answers send the link, so the only
    thing riding on it is which message wraps it."""
    return (
        s.get("partner_status") == "couple"
        and s.get("partner_can_join") is False
        and s.get("partner_is_decision_maker") is not False
    )


def _booking_action(s: dict) -> Action:
    """Which booking script to send. A couple whose partner will not join hears
    the couples expectation first; everyone else (solo, a partner who IS joining,
    or a woman who says she decides alone) gets the plain link."""
    if _shares_decision_but_absent(s):
        return Action.SEND_BOOKING_TOGETHER
    return Action.SEND_BOOKING


def _discovery_complete(s: dict) -> bool:
    return bool(
        s.get("trying_duration")
        and s.get("age")
        and (s.get("treatment_path") or s.get("what_tried"))
    )


def _financial_ok(s: dict) -> bool:
    # Confirmed open, OR the partner is the decision-maker (money is decided with
    # them on the call) and the lead has not explicitly declined.
    if s.get("financial_ready") is True:
        return True
    return s.get("partner_is_decision_maker") is True and s.get("financial_ready") is not False


def _role_ok(state: dict) -> bool:
    """Role step satisfied: she heard (and accepted) the not-a-doctor role, OR
    stated in her own words that she understands this is coaching, not medical
    care (Sonia v1.1: such a lead must not be re-run through EXPLAIN_ROLE) -
    and she never rejected the approach."""
    s, f = state["slots"], state["flags"]
    if s.get("open_to_holistic") is False:
        return False
    if s.get("understands_role") is True:
        return True
    return f.get("explained_role") is True and s.get("open_to_holistic") is True


def booking_gate(state: dict) -> bool:
    """Phase-7 checklist. SEND_BOOKING is only reachable when ALL are true."""
    s, f = state["slots"], state["flags"]
    return all([
        f.get("situation_shared") is True,
        _actively_ttc(s),
        _priority_ok(s),
        _role_ok(state),
        _financial_ok(s),
        f.get("oos_reason") is None,
        _partner_resolved(s),
    ])


# --- Fit assessment ----------------------------------------------------------

_DURATION_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?|a|an|couple(?: of)?|few)\s*(?P<unit>year|yr|month|mo|week|wk)",
    re.IGNORECASE,
)
_WORD_NUMBERS = {"a": 1, "an": 1, "couple": 2, "couple of": 2, "few": 3}
_UNIT_MONTHS = {"year": 12, "yr": 12, "month": 1, "mo": 1, "week": 0.25, "wk": 0.25}


def months_trying(trying_duration: Optional[str]) -> Optional[float]:
    """Parse her own words into months. None when unparseable - never guess.

    Handles "3 months", "about a year", "a couple of years", "6 weeks". A phrase
    we cannot read returns None, and every caller treats None as "unknown", not
    as zero.
    """
    if not trying_duration:
        return None
    match = _DURATION_RE.search(str(trying_duration))
    if not match:
        return None
    raw = match.group("num").lower()
    count = _WORD_NUMBERS.get(raw, None)
    if count is None:
        try:
            count = float(raw)
        except ValueError:
            return None
    return count * _UNIT_MONTHS[match.group("unit").lower()]


# Below this many months of trying, with nothing else going on, standard medical
# advice is simply to keep trying - so is Sonia's.
_EARLY_MONTHS = 6
_YOUNG_AGE = 35


def likely_not_a_fit(state: dict) -> bool:
    """True when her OWN STATED facts say she probably does not need this yet.

    Sonia's example: 29 years old, trying naturally for 3 months, nothing tried,
    no diagnosis. She wants that woman told honestly, not sold to.

    Deliberately a code predicate rather than an LLM judgement: "should she join"
    is an assessment of facts, and the model classifying it was unreliable. Every
    condition requires POSITIVE knowledge - an unknown age or an unparseable
    duration means we do not claim she is a poor fit.
    """
    s = state["slots"]
    age = s.get("age")
    months = months_trying(s.get("trying_duration"))
    if not isinstance(age, int) or months is None:
        return False
    return (
        age < _YOUNG_AGE
        and months < _EARLY_MONTHS
        and s.get("diagnosis") in (None, "none")
        and not s.get("what_tried")
        and not s.get("diagnosis_detail")
        and s.get("done_testing") is not True
        and s.get("treatment_path") in (None, "natural")
        and s.get("tubes_blocked") in (None, "none")
    )


# --- Out-of-scope checks -----------------------------------------------------

@dataclass(frozen=True)
class OosOutcome:
    """What an out-of-scope check found.

    `kind="oos"`   -> terminal decline: pause + tag, `reason` names it.
    `kind="clarify"` -> we need one more answer before we can judge; `action` is a
                        normal question and `phase` is where it belongs.
    """
    kind: str
    action: Action
    reason: Optional[str] = None
    phase: Optional[Phase] = None


def menopause_check(state: dict) -> Optional[OosOutcome]:
    """Age-first menopause assessment. Returns None when the lead is young with a
    stated (benign) reason, meaning the funnel continues."""
    s = state["slots"]
    age = s.get("age")
    if age is None:
        # Need her age to decide; ask it directly rather than the reason first.
        return OosOutcome("clarify", Action.ASK_MENOPAUSE_AGE, phase=Phase.DISCOVERY)
    if isinstance(age, int) and age >= 40:
        # 40+ with a menopause / long no-period signal -> out of scope.
        return OosOutcome("oos", Action.OOS_MENOPAUSE, reason="menopause_oos")
    # Younger than 40: the reason matters (benign irregularity vs premenopausal).
    if s.get("no_period_reason") is None:
        return OosOutcome("clarify", Action.ASK_MENOPAUSE_REASON, phase=Phase.DISCOVERY)
    return None


def oos_check(
    state: dict,
    *,
    delta_tubes_blocked: Optional[str] = None,
    oos_signal: str = "none",
) -> Optional[OosOutcome]:
    """Every out-of-scope rule, in the order the spec requires.

    The EXTRACTED FACTS are checked before the LLM's `oos_signal` so these never
    depend on the model remembering to set a flag: age is a number, so code
    decides, not the model. (This was a real bug - it used to rely on the signal
    and missed age 48.)

    `delta_tubes_blocked` is this turn's delta, not the merged slot: the one-tube
    acknowledgement is delta-keyed so it never re-fires on later turns.
    """
    s = state["slots"]

    age = s.get("age")
    if isinstance(age, int) and age > 46:
        return OosOutcome("oos", Action.OOS_AGE_OVER_46, reason="age_over_46")
    if s.get("tubes_blocked") == "both":
        return OosOutcome("oos", Action.OOS_BOTH_TUBES, reason="both_tubes_blocked")
    if s.get("no_period_over_year") is True:
        # 12+ months without a period -> review carefully REGARDLESS of age
        # (Sonia v1.1); never continue discovery or ask her age first.
        return OosOutcome("oos", Action.OOS_NO_PERIOD_12M, reason="no_period_over_12m")
    if delta_tubes_blocked == "one" and not (s.get("treatment_path") or s.get("what_tried")):
        # She just said one tube is blocked -> acknowledge the one-vs-both
        # difference once and ask her treatment stage (Sonia v1.1). Skipped when
        # her stage is already known.
        return OosOutcome("clarify", Action.ONE_TUBE_ACK, phase=Phase.DISCOVERY)

    if oos_signal == "deaf":
        return OosOutcome("oos", Action.OOS_DEAF, reason="oos_deaf")
    if oos_signal == "age_over_46":  # LLM flagged it but no numeric age parsed
        return OosOutcome("oos", Action.OOS_AGE_OVER_46, reason="age_over_46")
    if oos_signal == "blocked_tubes":
        if s.get("tubes_blocked") in (None, "unspecified"):
            return OosOutcome("clarify", Action.ASK_BOTH_TUBES, phase=Phase.DISCOVERY)
        # one blocked -> continue discovery (fall through)
    if oos_signal == "menopause_no_period":
        return menopause_check(state)  # None -> young + benign -> continue

    return None
