import logging
import re

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

SCORE_PATTERN = re.compile(r"\[SCORE:\s*([+-]?\d+)\]")

MEDICAL_DEFLECTION = (
    "I really appreciate you sharing that with me. For anything related to medical advice, "
    "diagnoses, or treatment plans, it's so important to speak directly with a qualified "
    "healthcare provider who knows your full history. I'm here to support your journey "
    "emotionally and help you take the next step when you're ready. 💛"
)

PLAIN_TEXT_INSTRUCTIONS = (
    "Always respond in plain text. "
    "Do not use markdown formatting, bullet points, numbered lists, headers, bold, italics, or code blocks."
)

BOOKING_LINK_INSTRUCTIONS = (
    "Never include a booking link or URL in your replies. "
    "If the user asks for a booking link or to schedule a call, tell them warmly that someone from the team "
    "will be in touch shortly to arrange a time — do not mention or insert any link."
)


SCORING_INSTRUCTIONS = """
At the end of your reply, append a score delta on its own line in the format [SCORE:N] where N is an integer between -20 and +20. This line must be the very last thing in your response and must not appear anywhere else.

Score delta guidelines:
- +10 to +20: User expresses strong readiness, asks about booking, mentions budget/timeline
- +5 to +9: User is curious, engaged, asking meaningful questions about fertility options
- 0 to +4: Neutral or supportive conversation
- -5 to -20: User expresses doubt, frustration, or disengagement

Do not explain the score. Do not use [SCORE:N] anywhere except the final line.
"""


# ── System Prompt Builder ──────────────────────────────────────────────────────

def build_system_prompt(cfg: dict) -> str:
    parts = []

    about    = cfg.get("prompt_about", "").strip()
    services = cfg.get("prompt_services", "").strip()
    tone     = cfg.get("prompt_tone", "").strip()
    if about or services or tone:
        if about:    parts.append(f"## About the Business\n{about}")
        if services: parts.append(f"## Service Offerings\n{services}")
        if tone:     parts.append(f"## Conversation & Tone\n{tone}")
    else:
        parts.append(
            "You are a warm, empathetic fertility coaching assistant. "
            "You help people explore their fertility journey with compassion and clarity."
        )

    parts.append(PLAIN_TEXT_INSTRUCTIONS)
    parts.append(BOOKING_LINK_INSTRUCTIONS)
    parts.append(SCORING_INSTRUCTIONS.strip())
    return "\n\n".join(parts)


# ── Guardrail Checkers ─────────────────────────────────────────────────────────

def _keyword_match(text: str, terms: list[str]) -> bool:
    """Case-insensitive whole-word match for any term in the list."""
    text_lower = text.lower()
    for term in terms:
        term_lower = term.lower().strip()
        if not term_lower:
            continue
        pattern = r"\b" + re.escape(term_lower) + r"\b"
        if re.search(pattern, text_lower):
            return True
    return False


def check_medical_blocklist(text: str, cfg: dict) -> bool:
    """Returns True if the user's incoming message triggers the medical blocklist."""
    raw = cfg.get("medical_blocklist", "").strip()
    if not raw:
        return False
    terms = [t.strip() for t in raw.splitlines() if t.strip()]
    return _keyword_match(text, terms)


# ── Score Parser ───────────────────────────────────────────────────────────────

def parse_score_from_response(text: str) -> tuple[str, int]:
    """
    Strips the [SCORE:N] marker from the final line of the model's reply.

    Returns a (clean_text, delta) tuple. If the marker is missing or malformed,
    delta defaults to 0 and any embedded occurrences are stripped from clean_text.
    """
    lines = text.rstrip().splitlines()
    if not lines:
        return text, 0

    last_line = lines[-1].strip()
    match = SCORE_PATTERN.fullmatch(last_line)
    if match:
        try:
            delta = int(match.group(1))
        except ValueError:
            delta = 0
        clean = "\n".join(lines[:-1]).rstrip()
        return clean, delta

    # Marker not on last line — strip any embedded occurrences and return delta=0
    clean = SCORE_PATTERN.sub("", text).strip()
    return clean, 0


# ── Main Entry Point ───────────────────────────────────────────────────────────

async def generate_reply(
    user_message: str,
    history: list,  # list of Conversation ORM objects (or objects with .role / .content)
    cfg: dict,
    user_first_name: str | None,
    openai_client: AsyncOpenAI,
) -> tuple[str, int, bool]:
    """
    Calls GPT-4o and returns (clean_reply, score_delta, booking_link_used).
    """
    system_prompt = build_system_prompt(cfg)

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

    # ── Prompt debug ────────────────────────────────────────────────────────────
    logger.info("──────────── OUTGOING PROMPT (%d messages) ────────────", len(messages))
    for i, m in enumerate(messages):
        role = m["role"].upper()
        content = m["content"]
        logger.info("[%d] %s:\n%s", i, role, content)
    logger.info("────────────────────────────────────────────────────────────────")

    response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.7,
        max_tokens=500,
    )

    raw_reply = response.choices[0].message.content or ""

    # ── Response debug ──────────────────────────────────────────────────────────
    usage = response.usage
    prompt_tokens    = usage.prompt_tokens     if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens     = usage.total_tokens       if usage else 0
    # gpt-4o pricing as of 2025: $2.50/1M input, $10.00/1M output
    input_cost  = prompt_tokens    / 1_000_000 * 2.50
    output_cost = completion_tokens / 1_000_000 * 10.00
    total_cost  = input_cost + output_cost

    logger.info("──────────── OPENAI RESPONSE ────────────────────────────────────")
    logger.info("Raw reply:\n%s", raw_reply)
    logger.info(
        "Tokens — prompt: %d | completion: %d | total: %d",
        prompt_tokens, completion_tokens, total_tokens,
    )
    logger.info(
        "Cost    — input: $%.6f | output: $%.6f | total: $%.6f",
        input_cost, output_cost, total_cost,
    )
    logger.info("Model: %s | Finish reason: %s", response.model, response.choices[0].finish_reason)
    logger.info("────────────────────────────────────────────────────────────────")

    clean_reply, delta = parse_score_from_response(raw_reply)

    return clean_reply, delta, False
