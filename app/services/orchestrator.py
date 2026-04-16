"""
Strategy Engine for the AI pipeline.

Takes the RouteContext from router.py and produces a TurnDirective:
a focused, 15-20 line writer_brief that tells the Writer Agent exactly
what to do this turn — instead of the 600-word system-prompt wall it had before.

Brief content (the _brief_* functions) lives in briefs.py.
This module owns: TurnDirective, goal selection, and build_turn_directive().
"""

from dataclasses import dataclass

from app.services.router import RouteContext
from app.services import briefs


@dataclass
class TurnDirective:
    """Everything the Writer Agent and downstream stages need for one turn."""

    goal: str           # named goal — drives writer_brief selection
    bubble_count: int   # 1 | 2 | 3

    # Carried from RouteContext — used for state persistence in webhook / simulate
    booking_fires_now: bool
    booking_ask_confirmation: bool
    booking_url: str
    mark_price_deflected: bool
    lead_score: int
    known_facts: str | None

    # The focused instruction handed to the Writer LLM (~15-20 lines)
    writer_brief: str

    # Matched pattern (if any) — carried so the quality gate can enforce it
    matched_pattern: tuple[str, str] | None = None


# ── Goal selection ────────────────────────────────────────────────────────────

def _determine_goal(route: RouteContext, turn_number: int, has_enough_data: bool) -> str:
    """Map RouteContext signals → a single named goal for this turn."""

    # Booking always takes priority
    if route.booking_fires_now:
        return "send_booking"
    if route.booking_ask_confirmation:
        return "confirm_booking"

    # Browsing / no personal context yet — only meaningful on the very first turns.
    # Mid-conversation a low_intent signal is almost always a misclassification.
    if route.low_intent and turn_number <= 1:
        return "low_intent"

    # Heavy emotion — grief, devastation, loss (suppress_question is the grief flag).
    # Cap the streak: after 1 pure empathize, move to empathize_qualify (ack + question).
    # After 2, move to qualify — she needs direction, not more reflection.
    if route.suppress_question:
        streak = route.empathize_streak
        if streak == 0:
            return "empathize"          # First acknowledgment — pure, no questions
        if streak == 1:
            return "empathize_qualify"  # Already acknowledged once — move forward gently
        return "qualify"                # Done acknowledging, time to lead

    # First message
    if route.is_first_message:
        return "open" if route.opening_variant else "open_context"

    # Mild distress — but only if we haven't already acknowledged last turn.
    # After one empathize_qualify response, move to qualify (lead, don't keep reflecting).
    if getattr(route, "emotion", "neutral") == "mild_distress" and not route.prior_empathize:
        return "empathize_qualify"

    # Pricing objection
    _is_pricing = route.matched_objection is not None and any(
        kw in route.matched_objection[0].lower()
        for kw in ("pricing", "price", "cost")
    )
    if _is_pricing:
        if not route.price_already_deflected:
            return "handle_pricing_deflect"
        return "handle_pricing_reveal" if route.lead_score > 50 else "handle_pricing_redirect"

    # Other objection
    if route.matched_objection:
        return "handle_objection"

    # Synthesis: turn 5+ with at least 3 known data points
    if turn_number >= 5 and has_enough_data:
        return "synthesise"

    # Approaching booking threshold
    if route.cta_line:
        return "nurture"

    # Nothing left to qualify — all key dimensions are answered.
    # Staying in qualify with no question to ask produces dead-end copy.
    # Move toward the zoom session: the brief for nurture makes the expert
    # observation and invites the conversation forward.
    if route.question_for_dim is None:
        return "nurture"

    # Default — pattern context (if any) is woven into the qualify brief
    return "qualify"


def _count_known_data_points(known_facts: str | None) -> int:
    """Each semicolon-separated fact in known_facts counts as one data point."""
    if not known_facts:
        return 0
    return len([f for f in known_facts.split(";") if f.strip()])


# ── Public entry point ────────────────────────────────────────────────────────

def build_turn_directive(
    route: RouteContext,
    cfg: dict,
    turn_number: int,
) -> TurnDirective:
    """
    Convert a RouteContext into a TurnDirective with a focused writer_brief.

    Args:
        route:       The RouteContext produced by router.build_route_context().
        cfg:         The business configuration dict.
        turn_number: Count of prior assistant messages (0 = very first AI reply).
    """
    has_enough_data = _count_known_data_points(route.known_facts) >= 3
    goal = _determine_goal(route, turn_number, has_enough_data)
    bubble_count = briefs.BUBBLE_COUNTS.get(goal, 2)

    streak = route.empathize_streak

    brief_builders: dict[str, object] = {
        "open":                    lambda: briefs.brief_open(route),
        "open_context":            lambda: briefs.brief_open_context(route),
        "empathize":               lambda: briefs.brief_empathize(),
        "empathize_qualify":       lambda: briefs.brief_empathize_qualify(route, turn_number, empathize_streak=streak),
        "qualify":                 lambda: briefs.brief_qualify(route, turn_number),
        "synthesise":              lambda: briefs.brief_synthesise(route),
        "handle_pricing_deflect":  lambda: briefs.brief_handle_pricing_deflect(),
        "handle_pricing_reveal":   lambda: briefs.brief_handle_pricing_reveal(cfg),
        "handle_pricing_redirect": lambda: briefs.brief_handle_pricing_redirect(),
        "handle_objection":        lambda: briefs.brief_handle_objection(route),
        "low_intent":              lambda: briefs.brief_low_intent(),
        "nurture":                 lambda: briefs.brief_nurture(route, turn_number),
        "confirm_booking":         lambda: briefs.brief_confirm_booking(route),
        "send_booking":            lambda: briefs.brief_send_booking(route),
    }

    writer_brief = brief_builders.get(goal, lambda: briefs.brief_qualify(route, turn_number))()  # type: ignore[operator]

    return TurnDirective(
        goal=goal,
        bubble_count=bubble_count,
        booking_fires_now=route.booking_fires_now,
        booking_ask_confirmation=route.booking_ask_confirmation,
        booking_url=route.booking_url,
        mark_price_deflected=route.mark_price_deflected,
        lead_score=route.lead_score,
        known_facts=route.known_facts,
        writer_brief=writer_brief,
        matched_pattern=route.matched_pattern,
    )
