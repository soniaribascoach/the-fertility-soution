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
    cost: float
    prompt_tokens: int
    completion_tokens: int
    model: str


# ── Constants ──────────────────────────────────────────────────────────────────

_INPUT_PRICE_PER_M  = 0.40   # $ per 1M input tokens  (gpt-4.1-mini)
_OUTPUT_PRICE_PER_M = 1.60   # $ per 1M output tokens (gpt-4.1-mini)

PLAIN_TEXT_INSTRUCTIONS = (
    "Always respond in plain text. "
    "Do not use markdown formatting, bullet points, numbered lists, headers, bold, italics, or code blocks. "
    "NEVER use an em-dash (—) under any circumstances. This is a hard rule with no exceptions. "
    "If you feel the urge to write —, use a comma, a period, or split into two sentences instead. "
    # ── Bubble structure ──────────────────────────────────────────────────────
    "Send replies as short message bubbles, the way someone texts naturally. "
    "Separate each bubble with \\n\\n — this makes each arrive as a separate message. "
    "HARD RULE: every bubble is exactly 1–2 sentences. No exceptions, not even for emotional replies. "
    "DEFAULT TO ONE BUBBLE. One bubble is the correct choice for most replies. "
    "An acknowledgment with a natural follow-up woven in at the end is still ONE bubble — "
    "example: 'That's a lot to have been through, how long have you been trying?' "
    "Do not split that into two messages. It is one natural thought. "
    "EXCEPTION: when a qualifying or direct question is the focus of its own bubble, "
    "let the acknowledgment land fully first as a complete bubble, then send the question "
    "as a second bubble. The acknowledgment must not feel interrupted. "
    "Use TWO bubbles only when the reply contains two genuinely separate thoughts "
    "that would feel disjointed or too rushed if combined. "
    "Use THREE bubbles only for the very heaviest moments — miscarriage, failed IVF, deep grief — "
    "and only when two bubbles genuinely aren't enough. "
    "Never use four bubbles except for the booking link sequence. "
    "Never pad to hit a number. If one bubble says it fully, send one. "
    "If you receive additional guidance (a scenario perspective, a question, a credibility point) — "
    "weave it into your existing bubbles. It is flavour, not extra content. Do not add bubbles for it. "
    # ── Voice and tone ────────────────────────────────────────────────────────
    "Write the way a real person texts: use contractions (I'm, you're, that's), "
    "use :) or :( naturally where it fits, and don't over-punctuate. "
    "Do NOT use therapy language or scripted empathy phrases. "
    "Never use the same phrase or expression twice across the conversation. "
    "If you said 'I'm so sorry' once, find a completely different way to express empathy next time. "
    "Vary your language turn by turn — same feeling, different words every time. "
    "Do not project emotions or assume how someone feels beyond what they actually said. "
    "If someone says their IVF failed, acknowledge the fact — not a wall of feelings they never mentioned. "
    "Short and honest lands harder than long and elaborate. "
    # ── Questions ─────────────────────────────────────────────────────────────
    "Ask at most ONE question per reply. If you have nothing meaningful to ask, ask nothing. "
    # ── Openers and repetition ────────────────────────────────────────────────
    "Vary how you open each message — never start two replies the same way. "
    "Never open a reply mid-conversation with 'Hi', 'Hey', 'Hello', 'I saw your message', "
    "'I'm glad you reached out', or any greeting-style phrase. Respond directly to what was just said. "
    # ── Mirroring ─────────────────────────────────────────────────────────────
    "When reflecting what the user said, capture the feeling and meaning, not their exact words. "
    "Paraphrase with warmth. Never repeat a user's phrase back verbatim. "
    # ── Heavy emotional moments ───────────────────────────────────────────────
    "For miscarriage, failed IVF, hopelessness, or deep grief — your ENTIRE reply is acknowledgment only. "
    "No question. No advice. No pivot to services or next steps. Save any question for the next turn. "
    "Keep it short. One or two sentences of genuine recognition. "
    "Do not over-explain the acknowledgment. One honest sentence is often enough. "
    # ── Memory ───────────────────────────────────────────────────────────────
    "Before asking any question, check the conversation history. "
    "Reference prior information naturally when relevant: 'Since you've been trying for two years...', "
    "'Given your PCOS diagnosis...' — never re-ask something the person has already told you. "
    # ── Authenticity ─────────────────────────────────────────────────────────
    "Write like a real human who genuinely cares — not a polished AI assistant, not a sales agent. "
    "Imperfect and direct beats smooth and scripted every time."
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
        "Structure your reply as a natural 5-part sequence across short bubbles:\n"
        "1. Acknowledge what they have shared — one warm sentence that reflects their specific journey.\n"
        "2. Frame the next step naturally — e.g. 'The best next step from here is a call together.'\n"
        "3. Explain the value of the call in one sentence — clarity and a real plan, not a sales pitch.\n"
        "4. Ask for soft buy-in — e.g. 'Does that feel like a good next step for you?'\n"
        f"5. Share the link naturally as the final line — e.g. 'You can grab a time here: {url}'\n"
        f"The URL is: {url}\n"
        "Write in Sonia's voice throughout — warm, personal, not scripted. "
        "Do NOT say 'someone will reach out' or imply any delay."
    )

TAGGING_INSTRUCTIONS = """
Classify this conversation across 5 dimensions. Base your classification on the full conversation, not just the last message. If information is absent, use the most conservative tag.

Dimensions:
- ttc (time trying to conceive): ttc_0-6mo | ttc_6-12mo | ttc_1-2yr | ttc_2yr+. No info → ttc_0-6mo.
- diagnosis: diagnosis_none | diagnosis_suspected | diagnosis_confirmed. No info → diagnosis_none.
- urgency: urgency_low | urgency_medium | urgency_high. Mentions age or timeline pressure → urgency_high. No info → urgency_low.
- readiness: readiness_ready = asking to book, has budget, ready to start. readiness_considering = asking questions, weighing options. readiness_exploring = just browsing or unsure.
- fit: fit_high = serious, engaged, asking detailed questions. fit_medium = some engagement. fit_low = off-topic, venting only, or disengaged.

Emotional urgency signals — these MUST produce urgency_high, never lower:
- Any expression of hopelessness or desperation about conceiving: "I feel like it will never happen", "I give up", "I've tried everything and nothing works", "I feel so stuck", "I'm losing hope"
- Statements of exhaustion after long treatment journeys
- Doctor-framed urgency: "my doctor says IVF is my only option", "they recommended donor eggs" → urgency_high AND diagnosis_confirmed
Rule: hopelessness and desperation INCREASE urgency. Emotional distress never lowers the urgency tag.

Readiness signals:
- "I'm ready to try something different", "I want to do whatever it takes", "I'm serious about this" → readiness_considering or readiness_ready depending on context
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cfg(cfg: dict, key: str) -> str:
    return cfg.get(key, "").strip()


def _compute_cost(usage) -> tuple[int, int, float]:
    """Returns (prompt_tokens, completion_tokens, cost_usd)."""
    if usage is None:
        return 0, 0, 0.0
    pt = usage.prompt_tokens
    ct = usage.completion_tokens
    cost = (pt / 1_000_000 * _INPUT_PRICE_PER_M) + (ct / 1_000_000 * _OUTPUT_PRICE_PER_M)
    return pt, ct, cost


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

    about         = _cfg(cfg, "prompt_about")
    services      = _cfg(cfg, "prompt_services")
    tone          = _cfg(cfg, "prompt_tone")
    flow          = _cfg(cfg, "prompt_flow")
    hard_rules    = _cfg(cfg, "prompt_hard_rules")
    scoring_rules = _cfg(cfg, "prompt_scoring_rules")

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

    if hard_rules:
        parts.append(f"## Non-Negotiable Rules\n{hard_rules}")

    parts.append(PLAIN_TEXT_INSTRUCTIONS)
    parts.append(BOOKING_LINK_INSTRUCTIONS)  # overridden per-turn when booking_fires_now=True

    # Tagging instructions, optionally extended with business-defined signals
    tagging = TAGGING_INSTRUCTIONS.strip()
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

    if route.known_facts:
        parts.append(
            f"What you already know about this person — do NOT re-ask these:\n{route.known_facts}"
        )

    if route.opening_variant:
        parts.append(
            f"This is the lead's very first message. "
            f"If their message was a brief greeting or they haven't shared their situation yet, "
            f"open with this line (you may adapt the wording slightly but keep the spirit):\n"
            f"\"{route.opening_variant}\"\n"
            f"If they have already shared something personal — a diagnosis, a situation, how long they've been trying — "
            f"ignore this opener entirely and respond directly to what they said. "
            f"Never use this opener AND respond to their content in the same reply. Pick one."
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

    if route.low_intent:
        parts.append(
            "The user's intent is vague — they are just browsing or not sure what this is about. "
            "Gently ask what has brought them here personally before continuing. "
            "Do NOT describe services, pitch the program, or ask qualifying questions. "
            "Example: 'Of course — what's been going on for you lately?'"
        )

    if route.suppress_question:
        parts.append(
            "HEAVY EMOTIONAL MOMENT — do NOT ask any question in this reply, not even at the end. "
            "Do not offer advice, suggestions, or next steps. "
            "Your entire reply must be acknowledgment and emotional connection only."
        )
    elif route.question_for_dim:
        parts.append(
            f"Ask this question as its own bubble — after the acknowledgment has landed fully. "
            f"Preface it with a natural softener ('Just curious,' / 'I'm wondering,' / 'Out of curiosity,') "
            f"but only if it hasn't already appeared earlier in this conversation. "
            f"Ask only this one question, not multiple:\n"
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


# ── JSON Repair ───────────────────────────────────────────────────────────────

def _repair_json_newlines(raw: str) -> str:
    """
    Replace bare newline/carriage-return characters inside JSON string values
    with their escape sequences (\\n / \\r).  Structural whitespace outside
    strings is left untouched.
    """
    result: list[str] = []
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == "\\" and in_string:
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif ch == "\n" and in_string:
            result.append("\\n")
        elif ch == "\r" and in_string:
            result.append("\\r")
        else:
            result.append(ch)
    return "".join(result)


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
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Model emitted literal newlines inside the JSON string instead of \n escape sequences.
        # Walk the raw string and escape any bare newlines that appear inside a quoted value.
        data = json.loads(_repair_json_newlines(raw))
    clean_reply = data.get("reply", "").replace("—", ",")
    tags = data.get("tags", {})

    prompt_tokens, completion_tokens, total_cost = _compute_cost(response.usage)
    model_used = response.model or "gpt-4.1-mini"

    logger.info(
        "OpenAI — model: %s | tokens: %d in / %d out | cost: $%.5f | finish: %s",
        model_used, prompt_tokens, completion_tokens, total_cost,
        response.choices[0].finish_reason,
    )

    return ReplyResult(
        reply=clean_reply,
        tags=tags,
        cost=total_cost,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model_used,
    )
