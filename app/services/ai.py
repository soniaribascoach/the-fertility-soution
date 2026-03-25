import json
import logging
import re

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

TAGS_PATTERN = re.compile(
    r"\[TAGS:\s*"
    r"ttc=(?P<ttc>ttc_0-6mo|ttc_6-12mo|ttc_1-2yr|ttc_2yr\+)\s*\|\s*"
    r"diagnosis=(?P<diagnosis>diagnosis_none|diagnosis_suspected|diagnosis_confirmed)\s*\|\s*"
    r"urgency=(?P<urgency>urgency_low|urgency_medium|urgency_high)\s*\|\s*"
    r"readiness=(?P<readiness>readiness_exploring|readiness_considering|readiness_ready)\s*\|\s*"
    r"fit=(?P<fit>fit_low|fit_medium|fit_high)\s*\]"
)

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

TAGGING_INSTRUCTIONS = """
At the end of your reply, append a tag line as the very last line of your response in this exact format:
[TAGS: ttc=<ttc_tag> | diagnosis=<diag_tag> | urgency=<urgency_tag> | readiness=<readiness_tag> | fit=<fit_tag>]

Always output all 5 dimensions. Base classification on the full conversation, not just the last message. If information is absent, use the most conservative tag for that dimension.

Dimension values:
- ttc (time trying to conceive): ttc_0-6mo | ttc_6-12mo | ttc_1-2yr | ttc_2yr+
- diagnosis: diagnosis_none | diagnosis_suspected | diagnosis_confirmed
- urgency: urgency_low | urgency_medium | urgency_high
- readiness: readiness_exploring | readiness_considering | readiness_ready
- fit: fit_low | fit_medium | fit_high

Classification guidance:
- ttc: How long they've been trying. No info → ttc_0-6mo (most conservative).
- diagnosis: Whether they mention a fertility diagnosis. No info → diagnosis_none.
- urgency: How time-sensitive they feel. Mentions age/timeline pressure → urgency_high. No info → urgency_low.
- readiness: readiness_ready = asking to book, has budget, ready to start. readiness_considering = asking questions, weighing options. readiness_exploring = just browsing or unsure.
- fit: fit_high = serious, engaged, asking detailed questions. fit_medium = some engagement. fit_low = off-topic, venting only, or disengaged.

Do not explain the tags. Do not use [TAGS: ...] anywhere except the final line.
"""


# ── System Prompt Builder ──────────────────────────────────────────────────────

def build_system_prompt(cfg: dict) -> str:
    parts = []

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
            "You are a warm, empathetic fertility coaching assistant. "
            "You help people explore their fertility journey with compassion and clarity."
        )

    if flow:
        parts.append(f"## Conversation Flow\n{flow}")

    # Advanced AI Coaching fields
    hard_rules             = cfg.get("prompt_hard_rules", "").strip()
    opening_variants       = cfg.get("prompt_opening_variants", "").strip()
    qualification_qs       = cfg.get("prompt_qualification_questions", "").strip()
    pattern_responses      = cfg.get("prompt_pattern_responses", "").strip()
    objection_handling     = cfg.get("prompt_objection_handling", "").strip()
    authority_proof        = cfg.get("prompt_authority_proof", "").strip()
    cta_transitions        = cfg.get("prompt_cta_transitions", "").strip()

    if hard_rules:         parts.append(f"## Non-Negotiable Rules\n{hard_rules}")
    if opening_variants:   parts.append(f"## Opening Message Variants\n{opening_variants}")
    if qualification_qs:   parts.append(f"## Qualification Questions\n{qualification_qs}")
    if pattern_responses:  parts.append(f"## Pattern Recognition Responses\n{pattern_responses}")
    if objection_handling: parts.append(f"## Objection Handling\n{objection_handling}")
    if authority_proof:    parts.append(f"## Authority & Proof Phrases\n{authority_proof}")
    if cta_transitions:    parts.append(f"## CTA Transition Lines\n{cta_transitions}")

    parts.append(PLAIN_TEXT_INSTRUCTIONS)
    parts.append(BOOKING_LINK_INSTRUCTIONS)

    # Build tagging instructions, optionally with custom scoring guidance
    tagging = TAGGING_INSTRUCTIONS.strip()
    scoring_rules = cfg.get("prompt_scoring_rules", "").strip()
    if scoring_rules:
        tagging += f"\n\nAdditional scoring guidance from the business:\n{scoring_rules}"
    parts.append(tagging)

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


def check_human_takeover_triggers(text: str, cfg: dict) -> bool:
    """Returns True if the user's incoming message triggers a human takeover."""
    raw = cfg.get("human_takeover_triggers", "").strip()
    if not raw:
        return False
    terms = [t.strip() for t in raw.splitlines() if t.strip()]
    return _keyword_match(text, terms)


# ── Tag Parser ─────────────────────────────────────────────────────────────────

def parse_tags_from_response(text: str) -> tuple[str, dict[str, str]]:
    """
    Strips the [TAGS: ...] marker from the final line of the model's reply.

    Returns a (clean_text, tags_dict) tuple. If the marker is missing or malformed,
    tags defaults to {} and any embedded occurrences are stripped from clean_text.
    """
    lines = text.rstrip().splitlines()
    if not lines:
        return text, {}

    last_line = lines[-1].strip()
    match = TAGS_PATTERN.search(last_line)
    if match and TAGS_PATTERN.fullmatch(last_line):
        tags = {
            "ttc": match.group("ttc"),
            "diagnosis": match.group("diagnosis"),
            "urgency": match.group("urgency"),
            "readiness": match.group("readiness"),
            "fit": match.group("fit"),
        }
        clean = "\n".join(lines[:-1]).rstrip()
        return clean, tags

    # Marker not on last line — strip any embedded occurrences and return empty tags
    clean = TAGS_PATTERN.sub("", text).strip()
    return clean, {}


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
    ttc_val      = _TTC_VAL.get(tags.get("ttc", "ttc_0-6mo"), 0)
    diag_val     = _DIAG_VAL.get(tags.get("diagnosis", "diagnosis_none"), 0)
    urgency_val  = _URGENCY_VAL.get(tags.get("urgency", "urgency_low"), 0)
    readiness_val = _READINESS_VAL.get(tags.get("readiness", "readiness_exploring"), 0)
    fit_val      = _FIT_VAL.get(tags.get("fit", "fit_low"), 0)

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
) -> tuple[str, dict[str, str], bool]:
    """
    Calls GPT-4o and returns (clean_reply, tags_dict, booking_link_used).
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

    clean_reply, tags = parse_tags_from_response(raw_reply)

    return clean_reply, tags, False
