"""
Context Router for the AI pipeline.

Two-stage process:
  Part A — deterministic signals: first message, tag gaps, CTA proximity
  Part B — LLM classifier (single cheap call): scenario, objection, emotion,
            booking_intent, pricing_asked, dims_answered

booking_intent, pricing_asked and dims_answered are intentionally owned by the
classifier rather than hardcoded regex/keyword lists. The classifier has full
conversation context and handles ambiguity far better than pattern matching
(e.g. "as soon as possible" as a booking signal, "fee" vs "feel", etc.).
"""
import json
import logging
import random
import re
from dataclasses import dataclass

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Tag defaults — dimensions at these values are considered "unknown"
_DEFAULT_TAGS = {
    "ttc": "ttc_0-6mo",
    "diagnosis": "diagnosis_none",
    "urgency": "urgency_low",
    "readiness": "readiness_exploring",
    "fit": "fit_low",
}

# Priority order for qualification question selection
_DIM_PRIORITY = ["ttc", "diagnosis", "urgency"]

# Dimension → keywords to find the right question in prompt_qualification_questions
_DIM_QUESTION_KEYWORDS = {
    "ttc":       ["long", "trying", "how long"],
    "diagnosis": ["diagnosis", "diagnosed"],
    "urgency":   ["age", "old", "timeline", "time"],
}

# Signals that a first message already contains personal context — skip generic opener.
# Used only on turn 0 (classifier is skipped then).
_CONTEXT_SIGNAL_RE = re.compile(
    r"\b(amh|ivf|iui|trying|tried|doctor|diagnosis|diagnosed|pregnant|fertility|"
    r"hormone|fsh|lh|pcos|endometriosis|miscarriage|period|cycle|clomid|letrozole|"
    r"inositol|supplement|specialist|clinic)\b",
    re.IGNORECASE,
)
_FIRST_MSG_CONTEXT_WORD_THRESHOLD = 15


def _first_message_has_context(msg: str) -> bool:
    """Return True if the first user message already contains personal context.
    Used to decide between `open` (generic opener) and `open_context` (respond directly)."""
    if len(msg.split()) >= _FIRST_MSG_CONTEXT_WORD_THRESHOLD:
        return True
    return bool(_CONTEXT_SIGNAL_RE.search(msg))


# Truly unambiguous grief terms for first-turn deterministic fallback.
# The classifier handles emotion detection for all subsequent turns — keep this minimal.
_FIRST_TURN_GRIEF_TERMS = [
    "miscarriage", "recurrent loss", "multiple miscarriages",
    "hopeless", "give up", "giving up",
    "devastated", "heartbroken",
    "lost hope", "losing hope",
    "failed ivf", "ivf fail", "ivf didn't work",
    "failed iui", "iui fail",
]

# ── Booking state helpers ────────────────────────────────────────────────────
# After BOOKING_ASKED, fire on scheduling language immediately.
_SCHEDULING_INTENT_RE = re.compile(
    r"\b(when are you|what time|what days|send me|send the link|how do i book|"
    r"where do i|what'?s the link|how do i sign|i already told|already told you)\b"
    r"|when (are|is) (you|it) (available|free|open)",
    re.IGNORECASE,
)

# Explicit rejection — the ONLY reason NOT to fire after already_asked.
_BOOKING_REJECTION_RE = re.compile(
    r"\b(not (ready|sure|interested|now)|maybe later|not yet|actually no|"
    r"changed my mind|never mind|no thanks|don'?t think so|not for me)\b",
    re.IGNORECASE,
)

# Pricing regex — used ONLY as turn-0 fallback (classifier handles turns 1+)
_PRICING_RE = re.compile(
    r"\b(how much|price|pricing|cost|afford|investment|fee|fees|charge|charges)\b"
    r"|what does it cost|what'?s the cost|what is the cost"
    r"|how much does|how much is|cost of the program|cost of this"
    r"|what do you charge|how much do you charge",
    re.IGNORECASE,
)


@dataclass
class RouteContext:
    is_first_message: bool
    opening_variant: str | None             # selected variant text for turn 0
    matched_pattern: tuple[str, str] | None  # (label, full_text) from LLM classifier
    matched_objection: tuple[str, str] | None  # (label, full_text) from LLM classifier
    question_for_dim: str | None            # one qualification question based on tag gaps
    authority_phrase: str | None            # one proof phrase when classifier says useful
    cta_line: str | None                    # one CTA line when score approaches threshold
    booking_fires_now: bool = False
    booking_ask_confirmation: bool = False
    booking_url: str = ""
    known_facts: str | None = None
    suppress_question: bool = False
    low_intent: bool = False
    lead_score: int = 0
    price_already_deflected: bool = False
    mark_price_deflected: bool = False
    emotion: str = "neutral"
    prior_empathize: bool = False       # True when the last AI turn was empathize/empathize_qualify
    empathize_streak: int = 0           # Count of consecutive empathize turns at end of history


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_list(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _parse_labeled_list(raw: str) -> list[tuple[str, str]]:
    pairs = []
    for line in _parse_list(raw):
        if ": " in line:
            label, text = line.split(": ", 1)
        else:
            words = line.split()
            label = " ".join(words[:3])
            text = line
        pairs.append((label.strip(), text.strip()))
    return pairs


_AGE_PATTERN = re.compile(r"\b(?:i[' ]?m|i am)\s+(\d{2})\b", re.IGNORECASE)


def _pick_authority_phrase(phrases: list[str], history: list) -> str | None:
    """Select an authority phrase not already used in this conversation.
    Shuffles the pool each call to vary selection order. Returns None when all are exhausted."""
    history_text = " ".join(
        (m.content or "") for m in history if m.role == "assistant"
    ).lower()
    # Shuffle so we don't always try phrases in the same order
    candidates = list(phrases)
    random.shuffle(candidates)
    for phrase in candidates:
        # Match on the first 40 chars — distinctive enough to detect re-use
        key = phrase.lower()[:40]
        if key not in history_text:
            return phrase
    return None  # all phrases already used — omit authority this turn


def _count_prior_empathize(history: list) -> int:
    """Count consecutive [EMPATHIZE]-flagged assistant turns at the end of history.

    Returns 0 if the last assistant message was not an empathize turn, 1 if it was,
    2+ if two or more consecutive empathize responses were given back-to-back.
    """
    count = 0
    for turn in reversed(history):
        if turn.role == "assistant" and turn.content:
            if "[EMPATHIZE]" in turn.content:
                count += 1
            else:
                break  # streak ended
    return count


def _derive_known_facts(prior_tags: dict, history: list | None = None) -> str | None:
    """Build a plain-English summary of what's already known so the writer doesn't re-ask."""
    parts = []

    ttc = prior_tags.get("ttc")
    if ttc and ttc != _DEFAULT_TAGS["ttc"]:
        label = {
            "ttc_6-12mo": "6–12 months",
            "ttc_1-2yr": "1–2 years",
            "ttc_2yr+": "over 2 years",
        }.get(ttc)
        if label:
            parts.append(f"how long they have been trying ({label}) — do not ask again")

    diagnosis = prior_tags.get("diagnosis")
    if diagnosis == "diagnosis_suspected":
        parts.append("they have a suspected diagnosis — do not ask if they have been diagnosed")
    elif diagnosis == "diagnosis_confirmed":
        parts.append("they have a confirmed diagnosis — do not ask if they have been diagnosed")

    urgency = prior_tags.get("urgency")
    if urgency in ("urgency_medium", "urgency_high"):
        parts.append("age or timeline pressure is already known — do not ask about this again")

    if history:
        user_texts = " ".join(t.content for t in history if t.role == "user" and t.content)
        user_lower = user_texts.lower()

        age_match = _AGE_PATTERN.search(user_texts)
        if age_match:
            parts.append(f"their age is {age_match.group(1)} — do not ask again")

        if "amh" in user_lower or "fsh" in user_lower or "antral" in user_lower:
            parts.append(
                "they have already shared bloodwork/test results — "
                "do NOT ask about hormone tests, blood tests, ultrasounds, or 'what testing have you had done'"
            )
        if "ivf" in user_lower or "iui" in user_lower:
            parts.append(
                "they have been through fertility treatment — "
                "do NOT ask whether they have seen a doctor, had testing done, or been to a clinic"
            )

    return "; ".join(parts) if parts else None


def _find_question_for_dim(dim: str, questions: list[str]) -> str | None:
    keywords = _DIM_QUESTION_KEYWORDS.get(dim, [])
    for q in questions:
        if any(kw in q.lower() for kw in keywords):
            return q
    return questions[0] if questions else None


def _select_question(
    prior_tags: dict,
    questions: list[str],
    dims_answered: list[str] | None = None,
) -> str | None:
    """Select the highest-priority unknown dimension question.

    Uses dims_answered from the classifier to skip dimensions the user already
    stated, even when the tagger still shows the default value (e.g. ttc_0-6mo
    for "only been trying 4 months" — which is both the real value AND the default).
    This ensures we always ask about the next genuinely unknown dimension.
    """
    if not questions:
        return None
    skip = set(dims_answered or [])
    for dim in _DIM_PRIORITY:
        if dim in skip:
            continue
        if prior_tags.get(dim, _DEFAULT_TAGS[dim]) == _DEFAULT_TAGS[dim]:
            q = _find_question_for_dim(dim, questions)
            if q:
                return q
    return None


# ── LLM Classifier ────────────────────────────────────────────────────────────

async def _run_classifier(
    user_message: str,
    history: list,
    pattern_pairs: list[tuple[str, str]],
    objection_pairs: list[tuple[str, str]],
    openai_client: AsyncOpenAI,
) -> tuple[
    tuple[str, str] | None,  # matched_pattern
    tuple[str, str] | None,  # matched_objection
    bool,                     # authority_useful
    bool,                     # low_intent
    str,                      # emotion
    bool,                     # booking_intent
    bool,                     # pricing_asked
    list[str],                # dims_answered
]:
    """
    Single LLM call classifying the full semantic context of the conversation.

    Returns 8 values. booking_intent, pricing_asked, and dims_answered replace the
    fragile keyword lists and regex that previously lived in build_route_context.
    """
    recent = []
    for turn in history[-6:]:
        if turn.role in ("user", "assistant") and turn.content:
            recent.append(f"{turn.role.upper()}: {turn.content}")
    recent.append(f"USER: {user_message}")
    convo = "\n".join(recent)

    scenario_list = (
        "\n".join(f"{i}. {label}" for i, (label, _) in enumerate(pattern_pairs))
        if pattern_pairs else "(none configured)"
    )
    objection_list = (
        "\n".join(f"{i}. {label}" for i, (label, _) in enumerate(objection_pairs))
        if objection_pairs else "(none configured)"
    )

    classifier_prompt = (
        "You are a conversation classifier. Analyze the conversation and return JSON.\n\n"
        f"Conversation:\n{convo}\n\n"
        f"Scenarios (return the best matching index, or -1 only if the user's situation genuinely doesn't relate to any — lean toward matching):\n{scenario_list}\n\n"
        f"Objections (return index or -1 if none clearly applies):\n{objection_list}\n"
        "Objections are ONLY about the coaching program itself (cost, scepticism, information overload). "
        "Emotional distress about a medical situation is NOT an objection.\n\n"
        "Classify each field:\n"
        "scenario: integer\n"
        "objection: integer\n"
        "authority_useful: true when it would feel natural for an expert to reference their track record — "
        "when sharing an insight, reframe, or perspective on her situation. "
        "Also true if the user questions whether the approach works or asks for proof. "
        "False for pure acknowledgment turns (grief, loss, devastation) and generic greetings.\n"
        "low_intent: true ONLY if there are ≤2 prior exchanges AND the user clearly has not shared anything "
        "personal yet. ALWAYS false if there are 3 or more prior exchanges.\n"
        "emotion: classify based on the user's CURRENT message (the last USER line) only — "
        "not the overall conversation context.\n"
        '  "grief" = the current message explicitly expresses grief/loss/hopelessness/devastation '
        '(e.g. "I feel like I\'ll never have a baby", "I\'m devastated", "we just lost another one")\n'
        '  "mild_distress" = the current message expresses worry, frustration, or overwhelm\n'
        '  "neutral" = the current message is informational, factual, a short reply, or conversational '
        '(e.g. "my AMH is 0.92", "thats what im not sure about", "no", "yes", "not really")\n'
        "Even if the overall conversation is heavy, if the current message is informational "
        'or a short reply, classify as "neutral".\n'
        "booking_intent: true if the user's latest message is a clear affirmative response to a direct "
        "invitation — yes, sure, ok, sounds good, absolutely, as soon as possible, right away, "
        "I'd love that, definitely, sign me up. "
        "Also true for scheduling language after the user has already been invited to book: "
        "'when are you available', 'what time works', 'send me the link', 'how do I book', "
        "or any implicit continuation that assumes the booking is happening. "
        "False for mid-conversation acknowledgments not responding to a direct invitation.\n"
        "pricing_asked: true if the user asks about price, cost, fees, investment, or affordability\n"
        "dims_answered: which qualification dimensions the user has explicitly stated anywhere in "
        "this conversation. Subset of [\"ttc\", \"diagnosis\", \"urgency\"].\n"
        "  ttc = user mentioned a specific duration trying to conceive (e.g. '4 months', '2 years')\n"
        "  diagnosis = user mentioned a specific condition or test result "
        "(AMH value, FSH, PCOS, endometriosis, thyroid, etc.)\n"
        "  urgency = user mentioned their age or expressed explicit time pressure\n\n"
        'Return only valid JSON: {"scenario": <int>, "objection": <int>, "authority_useful": <bool>, '
        '"low_intent": <bool>, "emotion": <str>, "booking_intent": <bool>, '
        '"pricing_asked": <bool>, "dims_answered": <list[str]>}'
    )

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": classifier_prompt}],
            temperature=0,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content or "{}")

        scenario_idx     = int(data.get("scenario", -1))
        objection_idx    = int(data.get("objection", -1))
        authority_useful = bool(data.get("authority_useful", False))
        low_intent       = bool(data.get("low_intent", False))
        emotion          = data.get("emotion", "neutral")
        booking_intent   = bool(data.get("booking_intent", False))
        pricing_asked    = bool(data.get("pricing_asked", False))
        dims_answered    = [
            d for d in data.get("dims_answered", [])
            if d in ("ttc", "diagnosis", "urgency")
        ]

        if emotion not in ("neutral", "mild_distress", "grief"):
            emotion = "neutral"

        matched_pattern   = pattern_pairs[scenario_idx]   if 0 <= scenario_idx  < len(pattern_pairs)   else None
        matched_objection = objection_pairs[objection_idx] if 0 <= objection_idx < len(objection_pairs) else None

        logger.debug(
            "Classifier → scenario=%s, objection=%s, emotion=%s, booking=%s, pricing=%s, dims=%s",
            matched_pattern[0] if matched_pattern else "none",
            matched_objection[0] if matched_objection else "none",
            emotion, booking_intent, pricing_asked, dims_answered,
        )
        return (
            matched_pattern, matched_objection, authority_useful,
            low_intent, emotion, booking_intent, pricing_asked, dims_answered,
        )

    except Exception as exc:
        logger.warning("Classifier call failed (%s) — using safe defaults", exc)
        return None, None, False, False, "neutral", False, False, []


# ── Public Entry Point ────────────────────────────────────────────────────────

async def build_route_context(
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
) -> RouteContext:
    is_first = len(history) == 0
    msg_lower = user_message.lower()

    # ── Turn-0 deterministic fallbacks ───────────────────────────────────────
    # Classifier is skipped on the first message — these only need to cover that case.
    suppress_question: bool = any(term in msg_lower for term in _FIRST_TURN_GRIEF_TERMS)
    pricing_asked_t0: bool  = bool(_PRICING_RE.search(msg_lower)) if is_first else False

    # ── Classifier (all turns after turn 0) ──────────────────────────────────
    matched_pattern: tuple[str, str] | None   = None
    matched_objection: tuple[str, str] | None = None
    authority_phrase: str | None              = None
    low_intent: bool                          = False
    emotion: str                              = "grief" if suppress_question else "neutral"
    booking_intent: bool                      = False
    pricing_asked: bool                       = pricing_asked_t0
    dims_answered: list[str]                  = []

    if not is_first:
        pattern_pairs     = _parse_labeled_list(cfg.get("prompt_pattern_responses", ""))
        objection_pairs   = _parse_labeled_list(cfg.get("prompt_objection_handling", ""))
        authority_phrases = _parse_list(cfg.get("prompt_authority_proof", ""))

        (
            matched_pattern, matched_objection, authority_useful,
            low_intent, emotion, booking_intent, pricing_asked, dims_answered,
        ) = await _run_classifier(
            user_message=user_message,
            history=history,
            pattern_pairs=pattern_pairs,
            objection_pairs=objection_pairs,
            openai_client=openai_client,
        )

        # Pattern match always warrants an authority reference — Sonia is sharing
        # expert knowledge she has seen many times; proof phrases land naturally there.
        if (authority_useful or matched_pattern is not None) and authority_phrases:
            authority_phrase = _pick_authority_phrase(authority_phrases, history)

        # Classifier is authoritative on grief — suppress questions on those turns
        if emotion == "grief":
            suppress_question = True

        # Low-intent only fires on very early turns — mid-conversation it's almost always wrong
        if low_intent and len(history) >= 4:
            low_intent = False

    # ── Opening variant (turn 0 only) ─────────────────────────────────────────
    opening_variant: str | None = None
    if is_first:
        variants = _parse_list(cfg.get("prompt_opening_variants", ""))
        if variants:
            opening_variant = random.choice(variants)
        # User already shared rich context → skip the generic opener, respond directly
        if opening_variant and _first_message_has_context(user_message):
            opening_variant = None
    if suppress_question:
        opening_variant = None  # never use a generic opener on a grief turn

    # ── Known facts ───────────────────────────────────────────────────────────
    known_facts = _derive_known_facts(prior_tags, history) if not is_first else None

    # ── Qualification question ────────────────────────────────────────────────
    # dims_answered (from classifier) skips dimensions the user already stated,
    # so we always ask about the next genuinely unknown dimension.
    question_for_dim: str | None = None
    if not is_first and not suppress_question:
        question_for_dim = _select_question(
            prior_tags,
            _parse_list(cfg.get("prompt_qualification_questions", "")),
            dims_answered=dims_answered,
        )

    # ── Pricing detection ─────────────────────────────────────────────────────
    if pricing_asked and matched_objection is None:
        matched_objection = ("Cost objection", "")
    _is_pricing = pricing_asked or (
        matched_objection is not None
        and any(kw in matched_objection[0].lower() for kw in ("pricing", "price", "cost"))
    )
    mark_price_deflected = pricing_asked and not price_already_deflected
    if _is_pricing:
        question_for_dim = None

    # ── Booking phase ─────────────────────────────────────────────────────────
    score_qualifies     = threshold > 0 and current_score >= threshold
    # Soft trigger: 80% of threshold after 5+ assistant turns.
    # Raised from 3 to prevent booking firing after just 3 turns on high-signal first messages
    # (e.g. a user who mentions AMH + age 38 + IVF in turn 1 can hit threshold immediately).
    assistant_turns     = sum(1 for t in history if t.role == "assistant")
    score_soft          = (
        threshold > 0
        and current_score >= int(threshold * 0.80)
        and assistant_turns >= 5
    )

    booking_fires_now        = False
    booking_ask_confirmation = False

    if not already_sent and not suppress_question:
        if already_asked and booking_intent:
            booking_fires_now = True
        elif already_asked and not _BOOKING_REJECTION_RE.search(user_message):
            # User was already invited to book and hasn't explicitly rejected.
            # Fire on scheduling language OR short replies (≤5 words) — they've already said yes once.
            if _SCHEDULING_INTENT_RE.search(user_message) or len(user_message.split()) <= 5:
                booking_fires_now = True
        elif booking_intent and pricing_asked and not already_asked:
            # User said "yes" AND asked about price in the same message.
            # Booking intent takes priority — don't abandon the conversion to deflect pricing.
            # confirm_booking goal will handle both; pricing context is addressed in the brief.
            booking_ask_confirmation = True
        elif price_already_deflected and score_qualifies and booking_intent:
            booking_fires_now = True
        elif (score_qualifies or score_soft) and not already_asked and assistant_turns >= 5:
            # Turn gate: minimum 5 AI turns before any booking invitation.
            # Prevents premature booking asks on high-signal first messages.
            logger.info(
                "Booking ask triggered — assistant_turns=%d, score=%d, threshold=%d",
                assistant_turns, current_score, threshold,
            )
            booking_ask_confirmation = True

    # ── CTA line ──────────────────────────────────────────────────────────────
    cta_line: str | None = None
    if not suppress_question and not booking_fires_now and not booking_ask_confirmation:
        if threshold > 0 and current_score >= int(threshold * 0.75):
            cta_options = _parse_list(cfg.get("prompt_cta_transitions", ""))
            if cta_options:
                cta_line = random.choice(cta_options)

    # ── Booking URL validation ────────────────────────────────────────────────
    booking_url = cfg.get("booking_link", "").strip() if booking_fires_now else ""
    if booking_fires_now and not booking_url:
        booking_fires_now = False
        if not already_asked:
            booking_ask_confirmation = True

    empathize_streak = _count_prior_empathize(history) if not is_first else 0
    prior_empathize = empathize_streak > 0

    return RouteContext(
        is_first_message=is_first,
        opening_variant=opening_variant,
        matched_pattern=matched_pattern,
        matched_objection=matched_objection,
        question_for_dim=question_for_dim,
        authority_phrase=authority_phrase,
        cta_line=cta_line,
        booking_fires_now=booking_fires_now,
        booking_ask_confirmation=booking_ask_confirmation,
        booking_url=booking_url,
        known_facts=known_facts,
        suppress_question=suppress_question,
        low_intent=low_intent,
        lead_score=current_score,
        price_already_deflected=price_already_deflected,
        mark_price_deflected=mark_price_deflected,
        emotion=emotion,
        prior_empathize=prior_empathize,
        empathize_streak=empathize_streak,
    )
