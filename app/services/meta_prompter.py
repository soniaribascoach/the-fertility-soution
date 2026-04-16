"""
Meta-prompter for the AI pipeline.

Replaces the router (context classifier) + orchestrator (strategy engine) + briefs
with a single LLM call that reads the full conversation and the behavioural
specification, then writes a hyper-specific writer brief for this turn.

The "one big static prompt" is:
  AI_BEHAVIOUR.md  +  business config (about, services, pricing, patterns, etc.)

This is assembled once per call in _build_meta_spec() and kept stable.
The per-turn input is just the conversation + current state.
"""

from __future__ import annotations

import json
import logging
import os
import re
import random

from openai import AsyncOpenAI

from app.services.orchestrator import TurnDirective

logger = logging.getLogger(__name__)


# ── Load the behavioural spec from disk ──────────────────────────────────────

_BEHAVIOUR_SPEC_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "AI_BEHAVIOUR.md")
)

try:
    with open(_BEHAVIOUR_SPEC_PATH, encoding="utf-8") as _f:
        _BEHAVIOUR_SPEC = _f.read().strip()
except FileNotFoundError:
    _BEHAVIOUR_SPEC = (
        "Sonia Ribas is a fertility coach with 15+ years experience and 700+ successful pregnancies. "
        "She builds genuine connection, qualifies naturally, and guides women toward a zoom session."
    )
    logger.warning("AI_BEHAVIOUR.md not found at %s — using fallback spec", _BEHAVIOUR_SPEC_PATH)


# ── Pricing constants ─────────────────────────────────────────────────────────

_META_INPUT_PRICE_PER_M  = 2.00   # gpt-4.1 input
_META_OUTPUT_PRICE_PER_M = 8.00   # gpt-4.1 output


# ── Known-facts helper (deterministic, same as router._derive_known_facts) ───

_AGE_RE = re.compile(r"\b(?:i[' ]?m|i am)\s+(\d{2})\b", re.IGNORECASE)
_DEFAULT_TAGS = {
    "ttc":       "ttc_0-6mo",
    "diagnosis": "diagnosis_none",
    "urgency":   "urgency_low",
    "readiness": "readiness_exploring",
    "fit":       "fit_low",
}


def _derive_known_facts(prior_tags: dict, history: list | None = None) -> str | None:
    """Return a plain-English summary of what's known so the writer doesn't re-ask."""
    parts: list[str] = []

    ttc = prior_tags.get("ttc")
    if ttc and ttc != _DEFAULT_TAGS["ttc"]:
        label = {
            "ttc_6-12mo": "6–12 months",
            "ttc_1-2yr":  "1–2 years",
            "ttc_2yr+":   "over 2 years",
        }.get(ttc)
        if label:
            parts.append(f"trying for {label} — do not ask again")

    diag = prior_tags.get("diagnosis")
    if diag == "diagnosis_suspected":
        parts.append("suspected diagnosis — do not ask if diagnosed")
    elif diag == "diagnosis_confirmed":
        parts.append("confirmed diagnosis — do not ask if diagnosed")

    if prior_tags.get("urgency") in ("urgency_medium", "urgency_high"):
        parts.append("age/timeline pressure already known — do not ask again")

    if history:
        user_text = " ".join(t.content for t in history if t.role == "user" and t.content)
        m = _AGE_RE.search(user_text)
        if m:
            parts.append(f"age is {m.group(1)} — do not ask again")
        ul = user_text.lower()
        if "amh" in ul or "fsh" in ul or "antral" in ul:
            parts.append("bloodwork/test results shared — do NOT ask about hormone tests again")
        if "ivf" in ul or "iui" in ul:
            parts.append("fertility treatment history shared — do NOT ask if they've seen a doctor")

    return "; ".join(parts) if parts else None


# ── Static spec assembler ─────────────────────────────────────────────────────

def _build_meta_spec(cfg: dict) -> str:
    """
    Assemble the one big static prompt:
      AI_BEHAVIOUR.md  +  all relevant business config fields.

    This is the knowledge base the meta-prompter reasons against.
    It stays the same across turns — only the conversation changes.
    """
    sections: list[str] = [
        "=== SONIA'S BEHAVIOURAL SPECIFICATION ===",
        _BEHAVIOUR_SPEC,
    ]

    def _add(title: str, key: str) -> None:
        val = cfg.get(key, "").strip()
        if val:
            sections.append(f"\n=== {title} ===\n{val}")

    _add("ABOUT THE BUSINESS", "prompt_about")
    _add("SERVICES OFFERED", "prompt_services")
    _add("CONVERSATION TONE & EXAMPLES", "prompt_tone")
    _add("CONVERSATION FLOW", "prompt_flow")
    _add("PRICING HANDLING", "prompt_pricing")
    _add("SCENARIO RESPONSE PATTERNS", "prompt_pattern_responses")
    _add("OBJECTION HANDLING", "prompt_objection_handling")
    _add("AUTHORITY / PROOF PHRASES", "prompt_authority_proof")
    _add("CTA TRANSITION LINES", "prompt_cta_transitions")

    hard_rules = cfg.get("prompt_hard_rules", "").strip()
    if hard_rules:
        sections.append(f"\n=== HARD RULES (override everything — never violate) ===\n{hard_rules}")

    return "\n".join(sections)


# ── Goal taxonomy ─────────────────────────────────────────────────────────────

_GOAL_LIST = (
    "open | open_context | empathize | empathize_qualify | qualify | synthesise | "
    "nurture | handle_pricing_deflect | handle_pricing_reveal | handle_pricing_redirect | "
    "handle_objection | low_intent | confirm_booking | send_booking"
)

_GOAL_NOTES = """
Goal reference (choose the single most appropriate):
- open: first message, no personal context yet — use a configured opening variant
- open_context: first message but she already shared something personal — respond directly
- empathize: she shared grief/loss/devastation — PURE acknowledgment, no questions
- empathize_qualify: distress + still conversational — acknowledge + one gentle question
- qualify: ask the next most important unknown question (ttc, diagnosis, or urgency)
- synthesise: turn 5+ with 3+ known facts — connect the dots into a coherent picture
- nurture: approaching booking threshold — make an expert observation + introduce zoom session naturally
- handle_pricing_deflect: first pricing question — deflect warmly, NO price numbers
- handle_pricing_reveal: second pricing ask AND score is high — share the range
- handle_pricing_redirect: second pricing ask AND score is still low — continue deflecting
- handle_objection: non-pricing objection about the program
- low_intent: turns 0-1 and no personal context shared yet
- confirm_booking: score threshold reached and she hasn't been invited yet — ask "Does that feel right?"
- send_booking: she confirmed she wants a session — send the warm confirmation (URL appended automatically)
"""

# ── Per-turn state prompt builder ─────────────────────────────────────────────

def _build_state_block(
    prior_tags: dict,
    score: int,
    threshold: int,
    already_sent: bool,
    already_asked: bool,
    price_deflected: bool,
    history: list,
    user_message: str,
) -> str:
    known_facts = _derive_known_facts(prior_tags, history)
    tag_summary = ", ".join(f"{k}={v}" for k, v in prior_tags.items() if v) if prior_tags else "none yet"

    turns: list[str] = []
    for turn in history:
        if turn.role in ("user", "assistant") and turn.content:
            content = turn.content
            for marker in (" [BOOKING_SENT]", " [BOOKING_ASKED]", " [PRICE_DEFLECTED]", " [EMPATHIZE]"):
                content = content.replace(marker, "")
            label = "SONIA" if turn.role == "assistant" else "USER"
            turns.append(f"{label}: {content}")
    turns.append(f"USER: {user_message}")

    convo_block = "\n".join(turns) if turns else "(no prior conversation)"

    state_lines = [
        f"Lead score: {score} / threshold {threshold}",
        f"Booking link sent already: {'yes — do NOT send again' if already_sent else 'no'}",
        f"Booking invitation sent already: {'yes' if already_asked else 'no'}",
        f"Price deflection used: {'yes — second ask, may now reveal range if appropriate' if price_deflected else 'no'}",
        f"Tags: {tag_summary}",
    ]
    if known_facts:
        state_lines.append(f"Known facts (writer must NOT re-ask): {known_facts}")

    return (
        "=== CONVERSATION STATE ===\n"
        + "\n".join(state_lines)
        + "\n\n=== FULL CONVERSATION ===\n"
        + convo_block
    )


# ── Schema for structured output ──────────────────────────────────────────────

_META_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "meta_directive",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "goal":         {"type": "string"},
                "bubble_count": {"type": "integer"},
                "writer_brief": {"type": "string"},
            },
            "required": ["goal", "bubble_count", "writer_brief"],
            "additionalProperties": False,
        },
    },
}

_VALID_GOALS = {
    "open", "open_context", "empathize", "empathize_qualify", "qualify",
    "synthesise", "nurture", "handle_pricing_deflect", "handle_pricing_reveal",
    "handle_pricing_redirect", "handle_objection", "low_intent",
    "confirm_booking", "send_booking",
}

# Bubble count defaults — used as fallback if the LLM outputs something unexpected
_BUBBLE_DEFAULTS: dict[str, int] = {
    "open": 2, "open_context": 2, "empathize": 2, "empathize_qualify": 2,
    "handle_pricing_deflect": 2, "handle_pricing_reveal": 2, "handle_pricing_redirect": 2,
    "confirm_booking": 2, "send_booking": 2,
    "qualify": 1, "synthesise": 1, "handle_objection": 1, "nurture": 1, "low_intent": 1,
}


# ── Public entry point ────────────────────────────────────────────────────────

async def build_meta_directive(
    user_message: str,
    history: list,
    cfg: dict,
    prior_tags: dict,
    current_score: int,
    threshold: int,
    openai_client: AsyncOpenAI,
    already_sent: bool = False,
    already_asked: bool = False,
    price_already_deflected: bool = False,
    user_id: str | None = None,
) -> tuple[TurnDirective, int, int, float]:
    """
    Single LLM call that reads the full conversation + behavioural spec and
    produces a TurnDirective with a hyper-specific writer_brief.

    Returns (directive, prompt_tokens, completion_tokens, cost).
    """
    static_spec   = _build_meta_spec(cfg)
    state_block   = _build_state_block(
        prior_tags=prior_tags,
        score=current_score,
        threshold=threshold,
        already_sent=already_sent,
        already_asked=already_asked,
        price_deflected=price_already_deflected,
        history=history,
        user_message=user_message,
    )

    system_prompt = (
        f"{static_spec}\n\n"
        "=== YOUR JOB THIS TURN ===\n"
        "Read the conversation above and write a precise writer brief.\n\n"
        f"{_GOAL_NOTES}\n"
        "Writer brief rules:\n"
        "- 12–18 lines max\n"
        "- Reference her EXACT words, numbers, and phrases from the conversation\n"
        "- Name the single most important detail to anchor the reply to\n"
        "- Specify the question to ask (if any), or say NO QUESTION this turn\n"
        "- Include any scenario reframe or objection handling from the spec if relevant\n"
        "- For send_booking: the URL is appended automatically — do NOT include it in the brief\n"
        "- For handle_pricing_deflect: NEVER include price numbers or ranges in the brief\n\n"
        "Return JSON with these exact keys: goal, bubble_count, writer_brief"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": state_block},
    ]

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=messages,
            temperature=0.2,
            max_tokens=600,
            response_format=_META_SCHEMA,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("Meta-prompter failed (%s) — falling back to safe qualify brief", exc)
        data = {
            "goal": "qualify",
            "bubble_count": 1,
            "writer_brief": (
                "Write exactly 1 message. Lead the conversation. "
                "Make a specific observation based on what she has shared, "
                "then ask the most important unanswered question about her situation."
            ),
        }
        # Zero cost on failure
        _build_directive_from_data(data, cfg, prior_tags, history, current_score, already_sent, already_asked, price_already_deflected)
        return (
            _build_directive_from_data(data, cfg, prior_tags, history, current_score, already_sent, already_asked, price_already_deflected),
            0, 0, 0.0,
        )

    usage = response.usage
    pt = usage.prompt_tokens if usage else 0
    ct = usage.completion_tokens if usage else 0
    cost = (pt / 1_000_000 * _META_INPUT_PRICE_PER_M) + (ct / 1_000_000 * _META_OUTPUT_PRICE_PER_M)

    logger.info(
        "Meta-prompter — goal=%s | bubbles=%s | tokens: %d in / %d out | cost: $%.5f",
        data.get("goal", "?"), data.get("bubble_count", "?"), pt, ct, cost,
    )

    directive = _build_directive_from_data(
        data=data,
        cfg=cfg,
        prior_tags=prior_tags,
        history=history,
        current_score=current_score,
        already_sent=already_sent,
        already_asked=already_asked,
        price_already_deflected=price_already_deflected,
    )
    return directive, pt, ct, cost


def _build_directive_from_data(
    data: dict,
    cfg: dict,
    prior_tags: dict,
    history: list,
    current_score: int,
    already_sent: bool,
    already_asked: bool,
    price_already_deflected: bool,
) -> TurnDirective:
    """Map the meta-prompter's JSON output → a TurnDirective with all pipeline flags set."""
    goal = data.get("goal", "qualify")
    if goal not in _VALID_GOALS:
        logger.warning("Meta-prompter returned unknown goal %r — defaulting to qualify", goal)
        goal = "qualify"

    bubble_count = int(data.get("bubble_count", _BUBBLE_DEFAULTS.get(goal, 1)))
    bubble_count = max(1, min(3, bubble_count))  # clamp to [1, 3]

    writer_brief = str(data.get("writer_brief", "")).strip()
    if not writer_brief:
        writer_brief = "Write a focused, specific reply. Lead the conversation forward."

    # ── Derive pipeline flags from goal + state ───────────────────────────────

    # booking_fires_now: meta-prompter chose send_booking AND link is configured AND not already sent
    booking_url = cfg.get("booking_link", "").strip()
    booking_fires_now = (
        goal == "send_booking"
        and bool(booking_url)
        and not already_sent
    )
    # If no URL, fall back to confirmation ask
    if goal == "send_booking" and not booking_url:
        goal = "confirm_booking"

    booking_ask_confirmation = goal == "confirm_booking"
    mark_price_deflected     = goal == "handle_pricing_deflect" and not price_already_deflected

    known_facts = _derive_known_facts(prior_tags, history)

    return TurnDirective(
        goal=goal,
        bubble_count=bubble_count,
        booking_fires_now=booking_fires_now,
        booking_ask_confirmation=booking_ask_confirmation,
        booking_url=booking_url if booking_fires_now else "",
        mark_price_deflected=mark_price_deflected,
        lead_score=current_score,
        known_facts=known_facts,
        writer_brief=writer_brief,
        matched_pattern=None,  # meta-prompter handles patterns internally in the brief
    )
