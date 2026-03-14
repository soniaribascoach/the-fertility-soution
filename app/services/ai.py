import re
from openai import AsyncOpenAI

SCORE_PATTERN = re.compile(r"\[SCORE:([+-]?\d+)\]")

MEDICAL_DEFLECTION = (
    "I really appreciate you sharing that with me. For anything related to medical advice, "
    "diagnoses, or treatment plans, it's so important to speak directly with a qualified "
    "healthcare provider who knows your full history. I'm here to support your journey "
    "emotionally and help you take the next step when you're ready. 💛"
)

HARD_NO_FALLBACK = (
    "I want to make sure I'm giving you the best possible support. "
    "Let's focus on how we can help you move forward on your fertility journey. "
    "Is there something specific you'd like to explore?"
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


def build_system_prompt(cfg: dict) -> str:
    parts = []

    base_prompt = cfg.get("system_prompt", "").strip()
    if base_prompt:
        parts.append(base_prompt)
    else:
        parts.append(
            "You are a warm, empathetic fertility coaching assistant. "
            "You help people explore their fertility journey with compassion and clarity."
        )

    hard_nos_raw = cfg.get("hard_nos", "").strip()
    if hard_nos_raw:
        hard_nos_list = [t.strip() for t in hard_nos_raw.splitlines() if t.strip()]
        if hard_nos_list:
            formatted = "\n".join(f"- {t}" for t in hard_nos_list)
            parts.append(
                f"IMPORTANT — Never discuss, reference, or respond to the following topics:\n{formatted}\n"
                "If the user raises any of these topics, gently redirect the conversation."
            )

    parts.append(SCORING_INSTRUCTIONS.strip())
    return "\n\n".join(parts)


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


def check_hard_nos(text: str, cfg: dict) -> bool:
    """Returns True if the text contains a hard-no topic (should use fallback)."""
    raw = cfg.get("hard_nos", "").strip()
    if not raw:
        return False
    terms = [t.strip() for t in raw.splitlines() if t.strip()]
    return _keyword_match(text, terms)


def check_medical_blocklist(text: str, cfg: dict) -> bool:
    """Returns True if the user message triggers the medical blocklist."""
    raw = cfg.get("medical_blocklist", "").strip()
    if not raw:
        return False
    terms = [t.strip() for t in raw.splitlines() if t.strip()]
    return _keyword_match(text, terms)


def parse_score_from_response(text: str) -> tuple[str, int]:
    """
    Strips the [SCORE:N] marker from the final line.
    Returns (clean_text, delta). Delta defaults to 0 if marker absent or malformed.
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


async def generate_reply(
    user_message: str,
    history: list,  # list of Conversation ORM objects
    cfg: dict,
    user_first_name: str | None,
    openai_client: AsyncOpenAI,
) -> tuple[str, int]:
    """
    Calls GPT-4o and returns (clean_reply, score_delta).
    Applies hard-no guardrail on the AI response.
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

    response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.7,
        max_tokens=500,
    )

    raw_reply = response.choices[0].message.content or ""
    clean_reply, delta = parse_score_from_response(raw_reply)

    # Hard-no guardrail on AI output
    if check_hard_nos(clean_reply, cfg):
        return HARD_NO_FALLBACK, 0

    return clean_reply, delta
