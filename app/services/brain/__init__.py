"""The qualification-funnel brain.

`run_turn` is the single entry point used by both the background worker and the
admin sandbox. It orchestrates the deterministic pipeline:

    0. Safety gate (config phrases)   - no LLM
    1. Phase-1 CTA bypass             - no LLM
    2. Extractor                      - LLM #1 (strict JSON)
    3. Director (controller + build_directive) - no LLM (state machine + agenda)
    4. Voice                          - LLM #2 (generates every message), or a
                                        pinned verbatim decline for OOS turns
    5. Output validator               - no LLM (regenerate once, else fallback)
    6. Finalize -> TurnResult

Flow control, the booking gate, and the guardrails are code; the wording is
generated and grounded in what the lead said.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

from app.services.brain.constants import Action, Phase, normalize_lead_state
from app.services.brain.extractor import extract
from app.services.brain.controller import decide
from app.services.brain.directive import build_directive
from app.services.brain import voice
from app.services.brain.validator import validate_generated
from app.services.brain import scripts

logger = logging.getLogger(__name__)

# ManyChat tag applied whenever a turn needs human review (matches legacy worker).
HUMAN_REVIEW_TAG = 86596410

_MEDIA_URL_RE = re.compile(r"^https?://\S+$")


@dataclass
class TurnResult:
    reply_text: Optional[str]
    lead_state: dict
    pause: bool = False
    pause_reason: Optional[str] = None
    add_tag: bool = False
    qualified: bool = False
    action: Optional[str] = None
    usage: dict = field(default_factory=dict)
    violations: list = field(default_factory=list)


def _trailing_user_texts(history: list[dict]) -> list[str]:
    out = []
    for m in reversed(history):
        if m.get("role") == "user":
            out.append(m.get("content", "") or "")
        else:
            break
    return list(reversed(out))


def _check_phase1(cfg: dict, history: list[dict]) -> Optional[str]:
    """Exact CTA keyword as the only user message -> verbatim opener."""
    user_msgs = [m for m in history if m.get("role") == "user"]
    if len(user_msgs) != 1:
        return None
    keywords = {k.strip().lower() for k in (cfg.get("phase1_cta_keywords") or "").split("\n") if k.strip()}
    if not keywords:
        return None
    if user_msgs[0].get("content", "").strip().lower() not in keywords:
        return None
    return (cfg.get("phase1_opening_message") or "").strip() or None


def _safety_gate(cfg: dict, recent_texts: list[str], state: dict) -> Optional[TurnResult]:
    lowered = [t.strip().lower() for t in recent_texts if t.strip()]
    if not lowered:
        return None

    # Media (a bare URL message) -> human takeover.
    if any(_MEDIA_URL_RE.match(t.strip()) for t in recent_texts):
        state["phase"] = Phase.TAKEOVER.value
        state["flags"]["takeover_reason"] = "media_message"
        return TurnResult(reply_text=None, lead_state=state, pause=True,
                          pause_reason="media_message", add_tag=True, action="SAFETY_MEDIA")

    # Medical blocklist -> send the configured deflection + takeover.
    blocklist = [p.strip().lower() for p in (cfg.get("medical_blocklist") or "").split("\n") if p.strip()]
    if blocklist and any(any(p in t for p in blocklist) for t in lowered):
        deflection = (cfg.get("medical_deflection") or "").strip()
        state["phase"] = Phase.TAKEOVER.value
        state["flags"]["takeover_reason"] = "medical_deflection"
        return TurnResult(reply_text=deflection or None, lead_state=state, pause=True,
                          pause_reason="medical_deflection", add_tag=True, action="SAFETY_MEDICAL")

    # Human-takeover trigger phrases.
    triggers = [t.strip().lower() for t in (cfg.get("human_takeover_triggers") or "").split("\n") if t.strip()]
    if triggers and any(any(tr in t for tr in triggers) for t in lowered):
        state["phase"] = Phase.TAKEOVER.value
        state["flags"]["takeover_reason"] = "human_handover"
        return TurnResult(reply_text=None, lead_state=state, pause=True,
                          pause_reason="human_handover", add_tag=True, action="SAFETY_TRIGGER")

    return None


def _combine_usage(*usages: dict) -> dict:
    out = {"prompt_tokens": 0, "completion_tokens": 0, "token_cost": 0.0, "ai_model": None}
    for u in usages:
        if not u:
            continue
        out["prompt_tokens"] += u.get("prompt_tokens", 0) or 0
        out["completion_tokens"] += u.get("completion_tokens", 0) or 0
        out["token_cost"] += u.get("token_cost", 0.0) or 0.0
        out["ai_model"] = u.get("ai_model") or out["ai_model"]
    return out


async def run_turn(
    openai_client: AsyncOpenAI,
    history: list[dict],
    cfg: dict,
    lead_state: Optional[dict] = None,
    *,
    ig_user_id: str = "",
) -> TurnResult:
    state = normalize_lead_state(lead_state)
    recent = _trailing_user_texts(history)

    # 0) Safety gate (no LLM).
    gated = _safety_gate(cfg, recent, state)
    if gated is not None:
        return gated

    # 1) Phase-1 CTA bypass (no LLM).
    opener = _check_phase1(cfg, history)
    if opener:
        state["phase"] = Phase.DISCOVERY.value
        return TurnResult(reply_text=opener, lead_state=state, action=Action.PHASE1_OPENING.value)

    if not recent:
        # Nothing actionable from the lead; do nothing.
        return TurnResult(reply_text=None, lead_state=state, action="NOOP")

    # 2) Extract (LLM #1).
    extraction, ex_usage = await extract(openai_client, history, state["slots"])

    # 3) Decide (no LLM) -> 4) build the directive (mode + agenda + constraints).
    decision = decide(state, extraction, cfg, ig_user_id)
    state = decision.lead_state
    directive = build_directive(decision, cfg, ig_user_id)

    # Non-generated turns: human takeover (no text) or a pinned OOS decline (verbatim).
    if not directive.generate:
        return TurnResult(
            reply_text=directive.pinned_text, lead_state=state,
            pause=directive.pause, pause_reason=directive.pause_reason,
            add_tag=directive.add_tag, qualified=directive.qualified,
            action=directive.action.value, usage=ex_usage,
        )

    # 5) Voice (LLM #2) -> validate -> regenerate once -> fall back to approved script.
    text, gen_usage = await voice.generate(openai_client, history, directive)
    result = validate_generated(directive, text)
    if not result.ok:
        logger.info("Voice failed validation %s; regenerating", result.violations)
        text2, gen_usage2 = await voice.generate(openai_client, history, directive, temperature=0.0)
        gen_usage = _combine_usage(gen_usage, gen_usage2)
        if validate_generated(directive, text2).ok:
            text = text2
        else:
            logger.info("Voice failed twice; using approved fallback for %s", directive.action)
            text = _fallback_text(directive, cfg)
            result = validate_generated(directive, text)

    usage = _combine_usage(ex_usage, gen_usage)
    return TurnResult(
        reply_text=text, lead_state=state, pause=directive.pause,
        pause_reason=directive.pause_reason, add_tag=directive.add_tag,
        qualified=directive.qualified, action=directive.action.value,
        usage=usage, violations=result.violations,
    )


def _fallback_text(directive, cfg: dict) -> str:
    """The approved verbatim script for this turn (or a minimal safe discovery
    line if the action has no script). Worst-case output = today's safe behavior."""
    action = directive.action
    if action in scripts.SCRIPTS:
        return scripts.render(action, cfg)
    question = directive.reference_text or ""
    return f"Got it. {question}".strip()
