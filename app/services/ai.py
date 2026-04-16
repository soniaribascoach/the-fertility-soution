import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime

from openai import AsyncOpenAI

from app.services.orchestrator import TurnDirective

logger = logging.getLogger(__name__)

# ── Prompt file logger ────────────────────────────────────────────────────────
_PROMPT_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts.log")
_PROMPT_LOG_PATH = os.path.normpath(_PROMPT_LOG_PATH)

_prompt_file_handler = logging.FileHandler(_PROMPT_LOG_PATH, encoding="utf-8")
_prompt_file_handler.setLevel(logging.DEBUG)
_prompt_logger = logging.getLogger("prompt_trace")
_prompt_logger.setLevel(logging.DEBUG)
_prompt_logger.addHandler(_prompt_file_handler)
_prompt_logger.propagate = False


def _log_prompt(user_id: str | None, label: str, messages: list) -> None:
    """Writes a prompt snapshot to prompts.log in a readable format."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uid = user_id or "unknown"
    lines = [f"\n{'═' * 70}", f"{label.upper()}  {ts}  |  user={uid}", f"{'═' * 70}"]
    for i, msg in enumerate(messages):
        role = msg["role"].upper()
        content = msg["content"]
        lines.append(f"\n[{role}]")
        lines.append(content)
        if i < len(messages) - 1:
            lines.append(f"{'─' * 40}")
    _prompt_logger.debug("\n".join(lines))


@dataclass
class ReplyResult:
    reply: str
    tags: dict[str, str]
    cost: float
    prompt_tokens: int
    completion_tokens: int
    model: str


# ── Pricing constants ─────────────────────────────────────────────────────────

_INPUT_PRICE_PER_M  = 0.40   # $ per 1M input tokens  (gpt-4.1-mini — writer + tagger)
_OUTPUT_PRICE_PER_M = 1.60   # $ per 1M output tokens (gpt-4.1-mini — writer + tagger)

_QG_INPUT_PRICE_PER_M  = 1.10   # $ per 1M input tokens  (o4-mini — quality gate)
_QG_OUTPUT_PRICE_PER_M = 4.40   # $ per 1M output tokens (o4-mini — quality gate)


# ── Writer system prompt (short, focused — ~120 words) ────────────────────────

_WRITER_PERSONA = (
    "You are Sonia Ribas — fertility coach with 15+ years of experience and 700+ successful pregnancies. "
    "You have seen hundreds of cases. You recognise patterns quickly, speak with quiet confidence, "
    "and build trust through specificity and genuine care. "
    "You speak directly as Sonia in every message. Not an AI. Not an assistant. Sonia."
)

_WRITER_VOICE = (
    "Write the way a real person texts: contractions (I'm, you're, that's), natural rhythm, light punctuation. "
    "Use :) or :( when it fits naturally — not every message. Incomplete sentences are fine.\n"
    "Never use an em-dash (—). Use a comma or period instead, or split into two sentences.\n"
    "Never use markdown formatting, bullet points, numbered lists, headers, bold, or italics.\n"
    "Never open mid-conversation with 'Hi', 'Hey', 'Hello', 'I saw your message', 'I'm glad you reached out'.\n"
    "Banned phrases — rewrite any sentence containing these:\n"
    "  'I'm sorry to hear that' / 'What I'm hearing is' / 'That sounds difficult'\n"
    "  'I appreciate you sharing' / 'I understand how you must be feeling'\n"
    "  'I see this is a lot' / 'that's a lot to process' / 'feel free to share'\n"
    "  'I'm here to listen' / 'It can be really frustrating' / 'It can be really hard'\n"
    "  'you're not alone' / 'it's completely normal to feel' / 'I can imagine how'\n"
    "  'that must be hard' / 'that must be difficult' / 'I hear you' as hollow validation\n"
    "Never offer exercises, meditations, breathing practices, or routines in this chat. "
    "That is programme content — direct her to the zoom session.\n"
    "Ask at most ONE question per reply. Short, direct, answerable in a few words.\n"
    "Always refer to sessions as 'zoom sessions'. Never 'call'.\n"
    "Bubbles are separated by blank lines (\\n\\n). Each bubble is one short thought."
)


def _build_writer_persona_prompt(cfg: dict) -> str:
    """
    Builds the stable part of the writer system prompt: persona, voice, rules, context, playbook.
    The turn-specific writer_brief is injected separately as a second system message after history,
    so it is the freshest instruction at generation time.
    """
    hard_rules = cfg.get("prompt_hard_rules", "").strip()
    hard_rules_section = f"\nHARD RULES (non-negotiable — override everything else):\n{hard_rules}\n" if hard_rules else ""

    about = cfg.get("prompt_about", "").strip()
    services = cfg.get("prompt_services", "").strip()
    context_section = ""
    if about or services:
        parts = []
        if about:
            parts.append(f"About the business:\n{about}")
        if services:
            parts.append(f"Services offered:\n{services}")
        context_section = "\n\nBUSINESS CONTEXT:\n" + "\n\n".join(parts)

    # Scenario patterns are intentionally excluded here — the matched pattern (if any)
    # is injected per-turn via _pattern_context() inside the writer_brief, which sits
    # directly before the user message. Loading ALL patterns every turn buries the brief
    # and gives the writer irrelevant scenario context to wade through.

    return (
        f"{_WRITER_PERSONA}\n\n"
        f"{_WRITER_VOICE}"
        f"{hard_rules_section}"
        f"{context_section}"
    )


# ── Tagging constants ─────────────────────────────────────────────────────────

TAGGING_INSTRUCTIONS = """
Classify this conversation across 5 dimensions. Base your classification on the full conversation, not just the last message. If information is absent, use the most conservative tag.

Dimensions:
- ttc (time trying to conceive): ttc_0-6mo | ttc_6-12mo | ttc_1-2yr | ttc_2yr+. No info → ttc_0-6mo.
- diagnosis: diagnosis_none | diagnosis_suspected | diagnosis_confirmed. No info → diagnosis_none.
- urgency: urgency_low | urgency_medium | urgency_high. Mentions age or timeline pressure → urgency_high. No info → urgency_low.
- readiness: readiness_ready = asking to book, has budget, ready to start. readiness_considering = asking questions, weighing options. readiness_exploring = just browsing or unsure.
- fit: fit_high = serious, engaged, asking detailed questions. fit_medium = some engagement. fit_low = off-topic, venting only, or disengaged.

Urgency signals — these MUST produce urgency_high, never lower:
- Age 35 or older while trying to conceive → urgency_high
- Any mention of AMH, FSH, antral follicle count, or ovarian reserve concerns → urgency_high
- Doctor recommending IVF, IUI, or other fertility treatment → urgency_high
- Any expression of hopelessness or desperation: "I feel like it will never happen", "I give up", "I've tried everything", "I'm losing hope" → urgency_high
- Statements of exhaustion after long treatment journeys → urgency_high
Rule: urgency only goes UP, never down. Emotional distress and medical pressure are urgency signals.

Diagnosis signals:
- AMH value mentioned, or doctor recommending IVF/IUI → at minimum diagnosis_suspected
- "My doctor says IVF is my only option", "they recommended donor eggs", "diagnosed with PCOS/endometriosis/unexplained infertility" → diagnosis_confirmed
- Any mention of a specific fertility test result (AMH, FSH, antral follicle count) or specific condition name → diagnosis_suspected
- No medical context at all → diagnosis_none

Readiness signals — use the full conversation arc, not just the latest message:
- "I'm ready to try something different", "I want to do whatever it takes", "I'm serious about this" → readiness_considering or readiness_ready
- "I think I need to talk to someone", "I need support", "I want help with this" → readiness_considering
- Asking "what do you offer?", "how does this work?", "what's included?" → readiness_considering (actively investigating)
- Still in conversation after 3+ exchanges → at minimum readiness_considering (they've demonstrated engagement)
- Asking to book, confirming zoom session, expressing clear readiness → readiness_ready
- FLOOR RULE: readiness_ready is permanent. Once a user has confirmed interest or agreed to book, a follow-up question about price, logistics, or anything else does NOT lower readiness. It stays at readiness_ready.

Fit signals:
- Sharing specific medical details (AMH values, test results, diagnosis, treatment history) → fit_high
- Asking detailed questions about the program or approach → fit_high
- Casual agreement or short responses → fit_medium
- Off-topic, venting only, or clearly disengaged → fit_low
"""

_TAGGER_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "tags_only",
        "strict": True,
        "schema": {
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
}


# Ordering for each tag dimension — lower index = lower/earlier value.
# Used to enforce floors: a confirmed value can never regress to an earlier one.
_TAG_ORDER: dict[str, list[str]] = {
    "ttc":       ["ttc_0-6mo", "ttc_6-12mo", "ttc_1-2yr", "ttc_2yr+"],
    "diagnosis": ["diagnosis_none", "diagnosis_suspected", "diagnosis_confirmed"],
    "urgency":   ["urgency_low", "urgency_medium", "urgency_high"],
    "readiness": ["readiness_exploring", "readiness_considering", "readiness_ready"],
    "fit":       ["fit_low", "fit_medium", "fit_high"],
}


def _apply_tag_floors(new_tags: dict, prior_tags: dict) -> dict:
    """Ensure no dimension regresses below its previously confirmed value."""
    result = dict(new_tags)
    for dim, order in _TAG_ORDER.items():
        prior_val = prior_tags.get(dim)
        new_val   = result.get(dim)
        if prior_val in order and new_val in order:
            if order.index(new_val) < order.index(prior_val):
                result[dim] = prior_val
    return result


# ── Therapy phrase stripper ───────────────────────────────────────────────────

# Phrases that commonly open replies but are explicitly banned.
# Listed lowercase — matched against the lowercased start of the reply.
_THERAPY_SENTENCE_OPENINGS = [
    "thanks for sharing",
    "thank you for sharing",
    "i appreciate you sharing",
    "thanks for telling me",
    "thank you for telling me",
]


def _strip_opening_therapy(text: str) -> str:
    """
    Deterministically remove a therapy sentence that opens the reply.
    Only acts on the very first sentence — doesn't touch the rest of the reply.
    Runs after the quality gate as a final safety net.
    """
    text_lower = text.lower()
    for phrase in _THERAPY_SENTENCE_OPENINGS:
        if text_lower.startswith(phrase):
            # Remove the whole opening sentence
            dot = text.find(". ")
            if dot != -1:
                text = text[dot + 2:].strip()
            break
    return text


# ── Guardrail checkers ────────────────────────────────────────────────────────

def _keyword_match(text: str, terms: list[str]) -> bool:
    text_lower = text.lower()
    for term in terms:
        term_lower = term.lower().strip()
        if term_lower and term_lower in text_lower:
            return True
    return False


def check_medical_blocklist(text: str, cfg: dict) -> bool:
    raw = cfg.get("medical_blocklist", "").strip()
    if not raw:
        return False
    terms = [t.strip() for t in raw.splitlines() if t.strip()]
    return _keyword_match(text, terms)


def check_human_takeover_triggers(text: str, cfg: dict) -> bool:
    raw = cfg.get("human_takeover_triggers", "").strip()
    if not raw:
        return False
    terms = [t.strip() for t in raw.splitlines() if t.strip()]
    return _keyword_match(text, terms)


# ── Score computer ────────────────────────────────────────────────────────────

_TTC_VAL      = {"ttc_0-6mo": 0, "ttc_6-12mo": 1, "ttc_1-2yr": 2, "ttc_2yr+": 3}
_DIAG_VAL     = {"diagnosis_none": 0, "diagnosis_suspected": 1, "diagnosis_confirmed": 2}
_URGENCY_VAL  = {"urgency_low": 0, "urgency_medium": 1, "urgency_high": 2}
_READINESS_VAL = {"readiness_exploring": 0, "readiness_considering": 1, "readiness_ready": 2}
_FIT_VAL      = {"fit_low": 0, "fit_medium": 1, "fit_high": 2}


def compute_score(tags: dict[str, str]) -> int:
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


# ── Cost helper ───────────────────────────────────────────────────────────────

def _compute_cost_at(usage, in_price: float, out_price: float) -> tuple[int, int, float]:
    if usage is None:
        return 0, 0, 0.0
    pt = usage.prompt_tokens
    ct = usage.completion_tokens
    cost = (pt / 1_000_000 * in_price) + (ct / 1_000_000 * out_price)
    return pt, ct, cost


def _compute_cost(usage) -> tuple[int, int, float]:
    return _compute_cost_at(usage, _INPUT_PRICE_PER_M, _OUTPUT_PRICE_PER_M)


# ── JSON repair ───────────────────────────────────────────────────────────────

def _repair_json_newlines(raw: str) -> str:
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


# ── Substantive goals — shared by quality gate (checks 10-12) and retry loop ─

_SUBSTANTIVE_GOALS = {
    "qualify", "synthesise", "nurture", "empathize_qualify",
    "handle_objection", "open_context", "confirm_booking",
}


# ── Stage 4A: Writer agent ────────────────────────────────────────────────────

async def _generate_writer_reply(
    user_message: str,
    history: list,
    cfg: dict,
    user_first_name: str | None,
    directive: TurnDirective,
    openai_client: AsyncOpenAI,
    user_id: str | None = None,
    retry_critique: str | None = None,
) -> tuple[str, int, int, float, str]:
    """
    Calls gpt-4.1-mini to generate the reply text only (no tags).
    Returns (reply_text, prompt_tokens, completion_tokens, cost, model).

    The writer_brief is injected as a second system message AFTER the conversation
    history, so it is the freshest instruction at generation time — not buried in a
    500-word system prompt that the model's recency bias will ignore.
    """
    persona_prompt = _build_writer_persona_prompt(cfg)
    messages: list[dict] = [{"role": "system", "content": persona_prompt}]

    if user_first_name:
        messages.append({
            "role": "system",
            "content": f"The user's first name is {user_first_name}. Use it naturally where appropriate, but not in every message.",
        })

    # Full history for context (last 20 turns)
    for turn in history:
        if turn.role in ("user", "assistant") and turn.content:
            # Strip state markers from stored content before feeding to writer
            content = turn.content
            for marker in (" [BOOKING_SENT]", " [BOOKING_ASKED]", " [PRICE_DEFLECTED]", " [EMPATHIZE]"):
                content = content.replace(marker, "")
            messages.append({"role": turn.role, "content": content})

    # If this is a reflexion retry, inject the quality gate's critique before the brief
    # so the writer knows exactly what failed and what to fix.
    if retry_critique:
        messages.append({
            "role": "system",
            "content": (
                f"QUALITY GATE CRITIQUE — previous attempt failed substantive checks:\n{retry_critique}\n"
                "Rewrite the reply from scratch, addressing this issue specifically."
            ),
        })

    # Inject the turn-specific brief RIGHT before the current message — freshest instruction.
    messages.append({"role": "system", "content": f"YOUR TASK FOR THIS TURN:\n{directive.writer_brief}"})

    messages.append({"role": "user", "content": user_message})

    _log_prompt(user_id, "WRITER", messages)

    response = await openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.3,
        max_tokens=500,
    )

    reply = (response.choices[0].message.content or "").strip()
    pt, ct, cost = _compute_cost(response.usage)
    model = response.model or "gpt-4.1-mini"

    logger.info(
        "Writer — model: %s | tokens: %d in / %d out | cost: $%.5f | finish: %s",
        model, pt, ct, cost, response.choices[0].finish_reason,
    )
    return reply, pt, ct, cost, model


# ── Stage 4B: Tagger agent ────────────────────────────────────────────────────

async def _classify_tags(
    user_message: str,
    history: list,
    cfg: dict,
    openai_client: AsyncOpenAI,
    prior_tags: dict | None = None,
    user_id: str | None = None,
) -> tuple[dict[str, str], int, int, float]:
    """
    Classifies the 5 dimension tags from the conversation.
    Runs in parallel with the writer. Returns (tags, prompt_tokens, completion_tokens, cost).
    """
    # Last 10 turns is sufficient for accurate tagging
    recent_history = history[-10:]

    convo_lines = []
    for turn in recent_history:
        if turn.role in ("user", "assistant") and turn.content:
            content = turn.content
            for marker in (" [BOOKING_SENT]", " [BOOKING_ASKED]", " [PRICE_DEFLECTED]", " [EMPATHIZE]"):
                content = content.replace(marker, "")
            convo_lines.append(f"{turn.role.upper()}: {content}")
    convo_lines.append(f"USER: {user_message}")

    scoring_rules = cfg.get("prompt_scoring_rules", "").strip()
    extra = (
        "\n\nAdditional tagging signals from the business:\n" + scoring_rules
        if scoring_rules else ""
    )

    floor_section = ""
    if prior_tags:
        floor_section = (
            "\n\nPRIOR CONFIRMED VALUES (these are the floor — never regress below them):\n"
            + json.dumps(prior_tags)
            + "\nIf the user has not explicitly contradicted a dimension this turn, keep the prior value."
        )

    tagger_prompt = TAGGING_INSTRUCTIONS.strip() + extra + floor_section + "\n\nConversation:\n" + "\n".join(convo_lines)

    messages = [{"role": "user", "content": tagger_prompt}]
    _log_prompt(user_id, "TAGGER", messages)

    response = await openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0,
        max_tokens=80,
        response_format=_TAGGER_SCHEMA,
    )

    raw = response.choices[0].message.content or "{}"
    try:
        tags = json.loads(raw)
    except json.JSONDecodeError:
        tags = json.loads(_repair_json_newlines(raw))

    # Enforce floors deterministically — belt-and-suspenders after the LLM call
    if prior_tags:
        tags = _apply_tag_floors(tags, prior_tags)

    pt, ct, cost = _compute_cost(response.usage)
    logger.info("Tagger — tokens: %d in / %d out | cost: $%.5f", pt, ct, cost)
    return tags, pt, ct, cost


# ── Stage 5: Quality gate ─────────────────────────────────────────────────────

_PRICE_NUMBER_RE = re.compile(r"\$[\d,]+|\b\d+[\s\u00a0]*(dollars|usd)\b", re.IGNORECASE)


def _reply_contains_price(text: str) -> bool:
    """Return True if the reply contains a specific dollar/price figure."""
    return bool(_PRICE_NUMBER_RE.search(text))

def _extract_recent_openers(history: list, n: int = 3) -> list[str]:
    """Return the first 4 words of the last n assistant messages."""
    openers = []
    for turn in reversed(history):
        if turn.role == "assistant" and turn.content:
            content = turn.content
            for marker in (" [BOOKING_SENT]", " [BOOKING_ASKED]", " [PRICE_DEFLECTED]", " [EMPATHIZE]"):
                content = content.replace(marker, "")
            # Take first bubble's first few words
            first_bubble = content.split("\n\n")[0].strip()
            words = first_bubble.split()[:4]
            if words:
                openers.append(" ".join(words))
        if len(openers) >= n:
            break
    return openers


def _build_quality_prompt(
    reply: str,
    bubble_count: int,
    known_facts_line: str,
    openers_line: str,
    opener_check: str,
    pricing_deflect_check: str,
    substantive_check: str = "",
    retry_instruction: str = "",
) -> str:
    """Assemble the quality-gate reviewer prompt. Separated for readability and testability."""
    return (
        "You are a quality checker for a chatbot reply. Review the reply below and fix ONLY "
        "the specific issues listed. Return the corrected reply and nothing else.\n\n"
        f"Bubble limit: {bubble_count} (bubbles are separated by blank lines).\n\n"
        "Fix any of these issues that apply:\n"
        "1. Em-dash (—) used → replace with a comma, or split into two sentences\n"
        "2. More than one question mark in the whole reply → keep only the most important question, remove the rest\n"
        "3. Therapy or hollow language present → rewrite that sentence to be direct and specific instead:\n"
        "   - 'what I'm hearing is' / 'I'm sorry to hear that' / 'that sounds difficult'\n"
        "   - 'I appreciate you sharing' / 'thanks for sharing' / 'thank you for sharing'\n"
        "   - 'I understand how you must be feeling'\n"
        "   - 'I see this is a lot' / 'that's a lot to process' / 'that's a lot to take in'\n"
        "   - 'I'm here to listen' / 'feel free to share' / 'feel free to reach out'\n"
        "   - 'It can be really frustrating' / 'It can be really hard'\n"
        "   - 'you're not alone' / 'it's completely normal to feel'\n"
        "   - 'I can imagine how' / 'that must be hard' / 'that must be difficult'\n"
        "   - 'I hear you' / 'I see you' used as hollow validation\n"
        f"4. {known_facts_line} — if the reply re-asks something already known, remove or rephrase\n"
        f"5. Bubble count enforcement — bubble limit is {bubble_count}:\n"
        "   - If the reply has MORE bubbles than the limit, merge the extras into the preceding bubble. "
        "Remove the blank line separator and combine them naturally.\n"
        "   - STRICT: if the limit is 1, the entire reply must be one unbroken paragraph — "
        "remove ALL blank lines and merge into a single continuous message.\n"
        "   - Having FEWER bubbles than the limit is fine — do NOT add blank lines.\n"
        f"6. {openers_line} — if the reply opens the same way as a recent one, rephrase the first 3-4 words only\n"
        f"7. {opener_check}"
        f"8. {pricing_deflect_check}\n"
        "9. Question complexity — if the reply contains a question, check it: "
        "Is it answerable in a few words? Rewrite it if it matches any of these patterns:\n"
        "   - Compound (two topics at once): keep only the more important part\n"
        "   - Lifestyle/vague/open: 'What does a typical day look like?', 'How are you managing things?', "
        "'How have you been handling X and Y?'\n"
        "   - Emotional/process questions that invite venting rather than a short answer: "
        "'What part of this feels most overwhelming?', 'What would you want to explore first?', "
        "'What feels hardest right now?', 'What's been weighing on you most?'\n"
        "   - Gut-feel questions: 'What's your gut saying?', 'What does your gut tell you?', "
        "'What feels right to you?', 'What's your instinct saying?'\n"
        "   Good questions are short, specific, and answerable in 2-5 words: "
        "'How's your sleep been?', 'Any diagnosis yet?', 'Are you still cycling regularly?', "
        "'How long have you been trying?', 'Do you have any test results?'\n"
        f"{substantive_check}"
        f"{retry_instruction}"
        "\nReply to review:\n"
        "---\n"
        f"{reply}\n"
        "---\n\n"
        "Return ONLY the corrected reply (with the optional RETRY line if triggered). "
        "No other explanation or commentary."
    )


async def _quality_check(
    reply: str,
    bubble_count: int,
    known_facts: str | None,
    recent_openers: list[str],
    openai_client: AsyncOpenAI,
    user_id: str | None = None,
    goal: str = "",
    allow_retry: bool = False,
) -> tuple[str, int, int, float, bool, str]:
    """
    Reviewer pass (o4-mini) that catches hard rule violations and fixes them.

    When allow_retry=True and the goal is substantive, the gate also signals if a
    full rewrite is needed — it appends 'RETRY: <critique>' on the last line.

    Returns (corrected_reply, prompt_tokens, completion_tokens, cost, needs_retry, critique).
    """
    known_facts_line = (
        f"Known facts (do not re-ask): {known_facts}"
        if known_facts
        else "No known facts to check."
    )
    openers_line = (
        f"Recent reply openers to avoid repeating: {', '.join(repr(o) for o in recent_openers)}"
        if recent_openers
        else "No prior openers to check."
    )

    pricing_deflect_check = (
        "PRICING DEFLECT VIOLATION — the goal this turn was to redirect away from price, NOT reveal one. "
        "The reply contains a specific dollar amount or price number. Remove it entirely. "
        "Replace with: the right program depends on the level of support, which is worked out in the zoom session."
        if goal == "handle_pricing_deflect" and _reply_contains_price(reply)
        else "No pricing deflect check needed."
    )

    opener_check = (
        "7. Skip this check — booking confirmation turn, warm opener is intentional.\n"
        if goal == "send_booking" else
        "7. Generic booking-session opener — if the reply opens with 'I'm glad you're ready', "
        "'I'm glad to hear', 'Great news', 'Wonderful', 'Brilliant', or any generic affirmation "
        "not tied to her specific situation, rewrite the opening to reference something concrete "
        "she actually shared (her age, test result, timeline, or diagnosis).\n"
    )

    # Substantive checks — enforce expert voice, specificity, and directiveness.
    # Applied on guidance/qualification goals only. Skipped for pure empathy and booking turns.
    if goal in _SUBSTANTIVE_GOALS:
        facts_hint = f" Known facts: {known_facts}." if known_facts else ""
        substantive_check = (
            "\n10. Expert value — does the reply contain at least one concrete observation, reframe, "
            "or directional guidance? Pure mirroring (repeating back what she said without adding "
            "anything expert) is not acceptable. If absent, add one expert sentence — an observation, "
            f"a reframe, or a clear direction forward.{facts_hint}\n"
            "11. Specificity — does the reply reference at least one specific detail she shared "
            "(her age, AMH value, ttc duration, diagnosis, treatment history, or her exact phrasing)? "
            "If not, edit to anchor it to her actual situation. Generic fertility commentary that could "
            "apply to any woman is not acceptable.\n"
            "12. Passivity — does the reply lead the conversation forward, or does it only reflect "
            "back what she said? If the reply is entirely reactive with no observation, no perspective, "
            "and no direction, make it more directive by adding or replacing one sentence.\n"
        )
    elif goal == "empathize":
        substantive_check = (
            "\n10. Grief turn check — ensure the reply contains NO reframe, NO guidance, and NO zoom "
            "session reference. Pure acknowledgment only. Remove anything that redirects or teaches.\n"
            "11-12. Skip — not applicable on grief turns.\n"
        )
    else:
        substantive_check = "\n10-12. Skip — not applicable for this goal type.\n"

    # Reflexion retry instruction — only on the first quality gate pass for substantive goals.
    # If after all edits the reply is still substantively weak, the gate signals RETRY.
    retry_instruction = ""
    if allow_retry and goal in _SUBSTANTIVE_GOALS:
        retry_instruction = (
            "\nFINAL VERDICT — after making all edits above:\n"
            "If the reply is STILL substantively weak (no expert observation, no specific detail "
            "anchored to her situation, entirely passive) even after your best edits, append "
            "this line at the very end of your response — on its own line:\n"
            "RETRY: [1-2 sentence critique: what is still wrong and which specific detail the writer must anchor to]\n"
            "If the reply is acceptable after your edits, do NOT add a RETRY line.\n"
        )

    quality_prompt = _build_quality_prompt(
        reply=reply,
        bubble_count=bubble_count,
        known_facts_line=known_facts_line,
        openers_line=openers_line,
        opener_check=opener_check,
        pricing_deflect_check=pricing_deflect_check,
        substantive_check=substantive_check,
        retry_instruction=retry_instruction,
    )

    messages = [{"role": "user", "content": quality_prompt}]
    _log_prompt(user_id, "QUALITY", messages)

    response = await openai_client.chat.completions.create(
        model="o4-mini",
        messages=messages,
        max_completion_tokens=900,
    )

    raw_corrected = (response.choices[0].message.content or reply).strip()
    pt, ct, cost = _compute_cost_at(response.usage, _QG_INPUT_PRICE_PER_M, _QG_OUTPUT_PRICE_PER_M)

    # Parse optional RETRY sentinel from the last line
    needs_retry = False
    critique    = ""
    lines = raw_corrected.split("\n")
    if lines and lines[-1].strip().startswith("RETRY:"):
        critique    = lines[-1].strip()[6:].strip()
        raw_corrected = "\n".join(lines[:-1]).strip()
        needs_retry = bool(critique)
        logger.info("Quality gate — RETRY requested: %s", critique)

    logger.info(
        "Quality gate — tokens: %d in / %d out | cost: $%.5f | retry=%s",
        pt, ct, cost, needs_retry,
    )
    return raw_corrected, pt, ct, cost, needs_retry, critique


# ── Main entry point ──────────────────────────────────────────────────────────

async def generate_reply(
    user_message: str,
    history: list,
    cfg: dict,
    user_first_name: str | None,
    openai_client: AsyncOpenAI,
    directive: TurnDirective | None = None,
    prior_tags: dict | None = None,
    user_id: str | None = None,
) -> ReplyResult:
    """
    Multi-agent reply pipeline (v7 + Phase 2 + Phase 3):

      Stage 3B — Brief optimizer (refines static brief with her exact words/numbers)
      Stage 4A — Writer LLM    (reply text only, focused brief)     ┐ sequential after 3B
      Stage 4B — Tagger LLM   (5 dimension tags)                    ┘ parallel with 3B
      Stage 5  — Quality gate (fixes violations; signals RETRY if still weak)
      Stage 5B — Reflexion retry (re-runs writer with critique, if gate triggered it)

    Returns a ReplyResult with combined token costs from all stages.
    """
    goal = directive.goal if directive else "qualify"

    # ── Stages 3B + 4B in parallel ─────────────────────────────────────────────
    # Dynamic brief optimizer mines her actual words from the last 4 turns.
    # Tagger classifies the conversation independently — no dependency on the brief.
    (refined_brief, b_pt, b_ct, b_cost), (tags, t_pt, t_ct, t_cost) = await asyncio.gather(
        _generate_dynamic_brief(
            goal=goal,
            template_brief=directive.writer_brief if directive else "",
            history=history,
            known_facts=directive.known_facts if directive else None,
            matched_pattern=directive.matched_pattern if directive else None,
            openai_client=openai_client,
            user_id=user_id,
        ),
        _classify_tags(
            user_message=user_message,
            history=history,
            cfg=cfg,
            openai_client=openai_client,
            prior_tags=prior_tags,
            user_id=user_id,
        ),
    )

    # Swap in the refined brief — carry everything else from the original directive.
    if directive and refined_brief != directive.writer_brief:
        effective_directive = TurnDirective(
            goal=directive.goal,
            bubble_count=directive.bubble_count,
            booking_fires_now=directive.booking_fires_now,
            booking_ask_confirmation=directive.booking_ask_confirmation,
            booking_url=directive.booking_url,
            mark_price_deflected=directive.mark_price_deflected,
            lead_score=directive.lead_score,
            known_facts=directive.known_facts,
            writer_brief=refined_brief,
            matched_pattern=directive.matched_pattern,
        )
    else:
        effective_directive = directive or _null_directive()

    # ── Stage 4A: Writer ────────────────────────────────────────────────────────
    writer_reply, w_pt, w_ct, w_cost, model = await _generate_writer_reply(
        user_message=user_message,
        history=history,
        cfg=cfg,
        user_first_name=user_first_name,
        directive=effective_directive,
        openai_client=openai_client,
        user_id=user_id,
    )

    # ── Stage 5: Quality gate ───────────────────────────────────────────────────
    recent_openers = _extract_recent_openers(history)
    bubble_count   = effective_directive.bubble_count
    known_facts    = effective_directive.known_facts

    corrected_reply, q_pt, q_ct, q_cost, needs_retry, critique = await _quality_check(
        reply=writer_reply,
        bubble_count=bubble_count,
        known_facts=known_facts,
        recent_openers=recent_openers,
        openai_client=openai_client,
        user_id=user_id,
        goal=goal,
        allow_retry=True,
    )

    # ── Stage 5B: Reflexion retry ───────────────────────────────────────────────
    # Only triggered when the quality gate signals the reply is still substantively
    # weak after its own edits — a full rewrite is needed.
    r_pt = r_ct = r_cost = q2_pt = q2_ct = q2_cost = 0
    if needs_retry and goal in _SUBSTANTIVE_GOALS:
        retried_reply, r_pt, r_ct, r_cost, _ = await _generate_writer_reply(
            user_message=user_message,
            history=history,
            cfg=cfg,
            user_first_name=user_first_name,
            directive=effective_directive,
            openai_client=openai_client,
            user_id=user_id,
            retry_critique=critique,
        )
        # Final quality gate pass — no further retries
        corrected_reply, q2_pt, q2_ct, q2_cost, _, _ = await _quality_check(
            reply=retried_reply,
            bubble_count=bubble_count,
            known_facts=known_facts,
            recent_openers=recent_openers,
            openai_client=openai_client,
            user_id=user_id,
            goal=goal,
            allow_retry=False,
        )

    # ── Deterministic post-processing ──────────────────────────────────────────
    # These run last as a safety net — LLM calls can still miss hard rules.

    # Strip em-dashes that slipped through.
    # Use regex to consume surrounding spaces so " — " becomes ", " not " , "
    clean_reply = re.sub(r"\s*—\s*", ", ", corrected_reply)

    # Strip price numbers from pricing-deflect turns — the writer/quality gate are unreliable here
    if directive and directive.goal == "handle_pricing_deflect":
        clean_reply = _PRICE_NUMBER_RE.sub("varies depending on the level of support", clean_reply)

    # Strip therapy phrases that open the reply — quality gate occasionally misses these
    clean_reply = _strip_opening_therapy(clean_reply)

    # For send_booking: deterministically append the booking URL as the final bubble.
    # The writer generates 2 warm bubbles; we always append the link ourselves.
    # This prevents hallucinated scheduling questions when the writer ignores the brief.
    if directive and directive.goal == "send_booking" and directive.booking_url:
        # Remove any URL the writer may have tried to include (we supply the canonical one)
        clean_reply = re.sub(r"https?://\S+", "", clean_reply).strip().rstrip("\n")
        clean_reply = clean_reply + f"\n\nYou can grab a time here: {directive.booking_url}"

    total_pt   = w_pt + t_pt + q_pt + b_pt + r_pt + q2_pt
    total_ct   = w_ct + t_ct + q_ct + b_ct + r_ct + q2_ct
    total_cost = w_cost + t_cost + q_cost + b_cost + r_cost + q2_cost

    logger.info(
        "Pipeline total — model: %s | tokens: %d in / %d out | cost: $%.5f",
        model, total_pt, total_ct, total_cost,
    )

    return ReplyResult(
        reply=clean_reply,
        tags=tags,
        cost=total_cost,
        prompt_tokens=total_pt,
        completion_tokens=total_ct,
        model=model,
    )


def _null_directive() -> TurnDirective:
    """Fallback directive when none is provided (should not normally happen)."""
    from app.services.orchestrator import TurnDirective
    return TurnDirective(
        goal="qualify",
        bubble_count=2,
        booking_fires_now=False,
        booking_ask_confirmation=False,
        booking_url="",
        mark_price_deflected=False,
        lead_score=0,
        known_facts=None,
        writer_brief=(
            "Write 1-2 bubbles. Acknowledge what she said warmly and ask one natural follow-up question.\n"
            "Add at least one of: a reframe, a small insight, or directional guidance."
        ),
    )
