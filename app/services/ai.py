import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.services.router import RouteContext

logger = logging.getLogger(__name__)


@dataclass
class ReplyResult:
    reply: str
    tags: dict[str, str]
    booking_link_used: bool
    cost: float
    prompt_tokens: int
    completion_tokens: int
    model: str


# ── Constants ──────────────────────────────────────────────────────────────────

PLAIN_TEXT_INSTRUCTIONS = (
    "Always respond in plain text. "
    "Do not use markdown formatting, bullet points, numbered lists, headers, bold, italics, or code blocks. "
    "NEVER use an em-dash (—) under any circumstances. This is a hard rule with no exceptions. "
    "If you feel the urge to write —, use a comma, a period, or split into two sentences instead. "
    "Keep replies short and conversational: 1 to 4 sentences is ideal, never more than 5. "
    "Write the way a real person would in a text message: use contractions (I'm, you're, that's), "
    "use :) or :( naturally where it fits, and don't over-punctuate. "
    "Ask at most one question per message. "
    "Vary how you open each message — never start two replies the same way, and avoid repeating phrases like "
    "'I hear you', 'I understand', or 'I appreciate you sharing that' more than once in a conversation."
)

BOOKING_LINK_INSTRUCTIONS = (
    "Never include a booking link or URL in your replies. "
    "If the user asks to schedule a call or book a session, respond with enthusiasm and warmth — "
    "tell them it sounds like a great next step, and keep the conversation going naturally. "
    "Do not promise that someone will reach out or that a link is coming. "
    "You do not control when the booking link is sent — that happens automatically. "
    "Your job is only to have a warm, natural conversation."
)

def booking_fires_now_instruction(url: str) -> str:
    return (
        "OVERRIDE — the booking link must be included in your reply. "
        "Do NOT say 'someone will be in touch' or imply a delay. "
        f"End your message with the booking link embedded naturally as the final sentence. "
        f"The URL is: {url}\n"
        "Example closing: 'You can book your call here: {url}' — but write it in Sonia's voice, "
        "not as a template. The link should feel like a natural continuation of what you just said."
    )

TAGGING_INSTRUCTIONS = """
Classify this conversation across 5 dimensions. Base your classification on the full conversation, not just the last message. If information is absent, use the most conservative tag.

Dimensions:
- ttc (time trying to conceive): ttc_0-6mo | ttc_6-12mo | ttc_1-2yr | ttc_2yr+. No info → ttc_0-6mo.
- diagnosis: diagnosis_none | diagnosis_suspected | diagnosis_confirmed. No info → diagnosis_none.
- urgency: urgency_low | urgency_medium | urgency_high. Mentions age or timeline pressure → urgency_high. No info → urgency_low.
- readiness: readiness_ready = asking to book, has budget, ready to start. readiness_considering = asking questions, weighing options. readiness_exploring = just browsing or unsure.
- fit: fit_high = serious, engaged, asking detailed questions. fit_medium = some engagement. fit_low = off-topic, venting only, or disengaged.
"""

# JSON schema for structured output — guarantees reply + tags are always returned
_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "coaching_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "reply": {"type": "string"},
                "tags": {
                    "type": "object",
                    "properties": {
                        "ttc": {
                            "type": "string",
                            "enum": ["ttc_0-6mo", "ttc_6-12mo", "ttc_1-2yr", "ttc_2yr+"],
                        },
                        "diagnosis": {
                            "type": "string",
                            "enum": ["diagnosis_none", "diagnosis_suspected", "diagnosis_confirmed"],
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["urgency_low", "urgency_medium", "urgency_high"],
                        },
                        "readiness": {
                            "type": "string",
                            "enum": ["readiness_exploring", "readiness_considering", "readiness_ready"],
                        },
                        "fit": {
                            "type": "string",
                            "enum": ["fit_low", "fit_medium", "fit_high"],
                        },
                    },
                    "required": ["ttc", "diagnosis", "urgency", "readiness", "fit"],
                    "additionalProperties": False,
                },
            },
            "required": ["reply", "tags"],
            "additionalProperties": False,
        },
    },
}


# ── System Prompt Builder ──────────────────────────────────────────────────────

def build_base_prompt(cfg: dict) -> str:
    """
    Builds the stable system prompt: persona, business context, hard rules,
    formatting instructions, and tagging instructions.

    Advanced coaching fields (opening variants, qualification questions, pattern
    responses, objection handling, authority proof, CTA transitions) are NOT
    included here — they are injected per-turn via build_context_block().
    """
    parts = []

    # Persona header — must come first so the model adopts Sonia's identity immediately
    parts.append(
        "You are Sonia Ribas, a warm, empathetic fertility coach with over 15 years of experience "
        "and over 700 babies welcomed. You speak directly as Sonia in every message — never as an AI, "
        "never as an assistant."
    )

    about    = cfg.get("prompt_about", "").strip()
    services = cfg.get("prompt_services", "").strip()
    tone     = cfg.get("prompt_tone", "").strip()
    flow     = cfg.get("prompt_flow", "").strip()
    if about or services or tone:
        if about:    parts.append(f"## About the Business\n{about}")
        if services: parts.append(f"## Service Offerings\n{services}")
        if tone:     parts.append(f"## Conversation & Tone\n{tone}")
    else:
        parts.append(
            "You help people explore their fertility journey with compassion and clarity."
        )

    if flow:
        parts.append(f"## Conversation Flow\n{flow}")

    hard_rules = cfg.get("prompt_hard_rules", "").strip()
    if hard_rules:
        parts.append(f"## Non-Negotiable Rules\n{hard_rules}")

    parts.append(PLAIN_TEXT_INSTRUCTIONS)
    parts.append(BOOKING_LINK_INSTRUCTIONS)  # overridden per-turn when booking_fires_now=True

    # Tagging instructions, optionally extended with business-defined signals
    tagging = TAGGING_INSTRUCTIONS.strip()
    scoring_rules = cfg.get("prompt_scoring_rules", "").strip()
    if scoring_rules:
        tagging += (
            "\n\nAdditional tagging signals from the business — use these to inform your classification:\n"
            + scoring_rules
        )
    parts.append(tagging)

    return "\n\n".join(parts)


def build_context_block(route: RouteContext) -> str:
    """
    Builds a targeted directive block for this specific conversation turn.
    Only the signals that are active are included — typical output is 0–5 lines.
    """
    parts = []

    if route.booking_fires_now:
        parts.append(booking_fires_now_instruction(route.booking_url))

    if route.opening_variant:
        parts.append(
            f"This is the lead's very first message. "
            f"Your response MUST begin with this exact opening:\n\"{route.opening_variant}\""
        )

    if route.matched_pattern:
        label, text = route.matched_pattern
        parts.append(
            f"This conversation is about: {label}. "
            f"Ground your reply in this perspective (adapt naturally — do not copy verbatim):\n{text}"
        )

    if route.matched_objection:
        label, text = route.matched_objection
        parts.append(
            f"The user is expressing a concern ({label}). "
            f"Use this approach (adapt naturally — do not copy verbatim):\n{text}"
        )

    if route.question_for_dim:
        parts.append(
            f"Weave this question naturally into your response — ask only this one question, not multiple:\n"
            f"{route.question_for_dim}"
        )

    if route.authority_phrase:
        parts.append(
            f"Naturally incorporate this credibility point where it fits in your reply:\n"
            f"{route.authority_phrase}"
        )

    if route.cta_line:
        parts.append(
            f"Close your message with this transition (adapt naturally to the conversation flow):\n"
            f"{route.cta_line}"
        )

    if not parts:
        return ""

    return "## Guidance for This Specific Reply\n\n" + "\n\n".join(parts)


# Keep backward-compatible alias used by tests
def build_system_prompt(cfg: dict) -> str:
    return build_base_prompt(cfg)


# ── Guardrail Checkers ─────────────────────────────────────────────────────────

def _keyword_match(text: str, terms: list[str]) -> bool:
    """Case-insensitive substring match for any term in the list."""
    text_lower = text.lower()
    for term in terms:
        term_lower = term.lower().strip()
        if term_lower and term_lower in text_lower:
            return True
    return False


def check_medical_blocklist(text: str, cfg: dict) -> bool:
    """Returns True if the user's incoming message triggers the medical blocklist."""
    raw = cfg.get("medical_blocklist", "").strip()
    if not raw:
        return False
    terms = [t.strip() for t in raw.splitlines() if t.strip()]
    return _keyword_match(text, terms)


def check_human_takeover_triggers(text: str, cfg: dict) -> bool:
    """Returns True if the user's incoming message triggers a human takeover."""
    raw = cfg.get("human_takeover_triggers", "").strip()
    if not raw:
        return False
    terms = [t.strip() for t in raw.splitlines() if t.strip()]
    return _keyword_match(text, terms)


# ── Score Computer ─────────────────────────────────────────────────────────────

_TTC_VAL = {"ttc_0-6mo": 0, "ttc_6-12mo": 1, "ttc_1-2yr": 2, "ttc_2yr+": 3}
_DIAG_VAL = {"diagnosis_none": 0, "diagnosis_suspected": 1, "diagnosis_confirmed": 2}
_URGENCY_VAL = {"urgency_low": 0, "urgency_medium": 1, "urgency_high": 2}
_READINESS_VAL = {"readiness_exploring": 0, "readiness_considering": 1, "readiness_ready": 2}
_FIT_VAL = {"fit_low": 0, "fit_medium": 1, "fit_high": 2}


def compute_score(tags: dict[str, str]) -> int:
    """
    Computes a weighted score (0–100) from the 5 dimension tags.

    score = (ttc/3 × 10) + (diag/2 × 15) + (urgency/2 × 20) + (readiness/2 × 40) + (fit/2 × 15)
    """
    ttc_val       = _TTC_VAL.get(tags.get("ttc", "ttc_0-6mo"), 0)
    diag_val      = _DIAG_VAL.get(tags.get("diagnosis", "diagnosis_none"), 0)
    urgency_val   = _URGENCY_VAL.get(tags.get("urgency", "urgency_low"), 0)
    readiness_val = _READINESS_VAL.get(tags.get("readiness", "readiness_exploring"), 0)
    fit_val       = _FIT_VAL.get(tags.get("fit", "fit_low"), 0)

    score = (
        (ttc_val / 3 * 10)
        + (diag_val / 2 * 15)
        + (urgency_val / 2 * 20)
        + (readiness_val / 2 * 40)
        + (fit_val / 2 * 15)
    )
    return round(score)


# ── Main Entry Point ───────────────────────────────────────────────────────────

async def generate_reply(
    user_message: str,
    history: list,  # list of Conversation ORM objects (or objects with .role / .content)
    cfg: dict,
    user_first_name: str | None,
    openai_client: AsyncOpenAI,
    route: RouteContext | None = None,
) -> ReplyResult:
    """
    Calls gpt-4.1-mini with structured output and returns a ReplyResult.
    Tags are guaranteed via JSON schema — no regex parsing needed.

    If route is provided, targeted context directives are appended to the base
    system prompt so the AI uses the right opening variant, pattern response,
    objection handling, authority proof, CTA line, and qualification question
    for this specific turn.
    """
    system_prompt = build_base_prompt(cfg)
    if route is not None:
        context_block = build_context_block(route)
        if context_block:
            system_prompt = system_prompt + "\n\n" + context_block

    messages = [{"role": "system", "content": system_prompt}]

    # Inject first-name context if available
    if user_first_name:
        messages.append({
            "role": "system",
            "content": f"The user's first name is {user_first_name}. Use it naturally where appropriate.",
        })

    # Build history
    for turn in history:
        if turn.role in ("user", "assistant") and turn.content:
            messages.append({"role": turn.role, "content": turn.content})

    # Add current user message
    messages.append({"role": "user", "content": user_message})

    logger.debug("Sending %d messages to OpenAI", len(messages))

    response = await openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=650,
        response_format=_RESPONSE_SCHEMA,
    )

    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    clean_reply = data.get("reply", "").replace("—", ",")
    tags = data.get("tags", {})

    usage = response.usage
    prompt_tokens     = usage.prompt_tokens     if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens      = usage.total_tokens      if usage else 0
    # gpt-4.1-mini pricing: $0.40/1M input, $1.60/1M output
    total_cost = (prompt_tokens / 1_000_000 * 0.40) + (completion_tokens / 1_000_000 * 1.60)
    model_used = response.model or "gpt-4.1-mini"

    logger.info(
        "OpenAI — model: %s | tokens: %d in / %d out / %d total | cost: $%.5f | finish: %s",
        model_used, prompt_tokens, completion_tokens, total_tokens, total_cost,
        response.choices[0].finish_reason,
    )

    return ReplyResult(
        reply=clean_reply,
        tags=tags,
        booking_link_used=False,
        cost=total_cost,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model_used,
    )
