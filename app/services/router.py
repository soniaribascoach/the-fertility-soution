"""
Context Router for the AI pipeline.

Two-stage process:
  Part A — deterministic signals: first message, tag gaps, CTA proximity
  Part B — LLM classifier (single cheap call): scenario, objection, authority timing

The resulting RouteContext is passed to build_context_block() in ai.py,
which injects targeted directives into the system prompt before generation.
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

# Pattern labels that indicate a high-emotion turn — suppress qualification question
_HIGH_EMOTION_KEYWORDS = {"miscarriage", "ivf", "hopeless", "grief", "amh"}

# Direct terms to detect high-emotion content in the user message — deterministic, no classifier needed
_HIGH_EMOTION_USER_TERMS = [
    "miscarriage",
    "ivf fail", "failed ivf", "ivf didn't work", "ivf did not work",
    "iui fail", "failed iui",
    "hopeless",
    "never going to happen",
    "give up", "giving up",
    "devastated", "heartbroken",
    "lost hope", "losing hope",
    "tried everything",
    "nothing works", "nothing is working",
    "feel like it will never",
    "feel like it's never",
    "donor egg",
    "recurrent loss",
    "3 miscarriages", "4 miscarriages", "5 miscarriages",
    "multiple miscarriages",
]

# Dimension → keywords to find the right question in prompt_qualification_questions
_DIM_QUESTION_KEYWORDS = {
    "ttc":       ["long", "trying", "how long"],
    "diagnosis": ["diagnosis", "diagnosed"],
    "urgency":   ["age", "old", "timeline", "time"],
}


@dataclass
class RouteContext:
    is_first_message: bool
    opening_variant: str | None             # selected variant text for turn 0
    matched_pattern: tuple[str, str] | None  # (label, full_text) from LLM classifier
    matched_objection: tuple[str, str] | None  # (label, full_text) from LLM classifier
    question_for_dim: str | None            # one qualification question based on tag gaps
    authority_phrase: str | None            # one proof phrase when classifier says useful
    cta_line: str | None                    # one CTA line when score approaches threshold
    booking_fires_now: bool = False         # True when booking link should be embedded in this reply
    booking_ask_confirmation: bool = False  # True when buy-in question should be asked (no link yet)
    booking_url: str = ""                   # The URL to embed when booking_fires_now is True
    known_facts: str | None = None          # derived from prior_tags + history — prevents re-asking known info
    suppress_question: bool = False         # True for high-emotion turns (grief, IVF, miscarriage)
    low_intent: bool = False               # True when user is vaguely browsing, not yet sharing anything personal
    lead_score: int = 0                    # current lead quality score (0–100) for score-aware responses


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_list(raw: str) -> list[str]:
    """Split newline-delimited config value into non-empty lines."""
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _parse_labeled_list(raw: str) -> list[tuple[str, str]]:
    """
    Parse lines formatted as 'Label: full response text'.
    Falls back to using the first 3 words as the label if no colon separator.
    Returns list of (label, full_text) pairs.
    """
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


def _derive_known_facts(prior_tags: dict, history: list | None = None) -> str | None:
    """Convert non-default prior tags + conversation history into plain English facts the AI should not re-ask."""
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

    # Scan user messages in history for explicit facts
    if history:
        user_texts = " ".join(
            t.content for t in history if t.role == "user" and t.content
        )
        user_lower = user_texts.lower()

        age_match = _AGE_PATTERN.search(user_texts)
        if age_match:
            parts.append(f"their age is {age_match.group(1)} — do not ask again")

        if "amh" in user_lower:
            parts.append("they have mentioned AMH — reference it naturally when relevant")

        if "ivf" in user_lower:
            parts.append("they have mentioned IVF — reference it naturally when relevant")

        if "iui" in user_lower:
            parts.append("they have mentioned IUI — reference it naturally when relevant")

    return "; ".join(parts) if parts else None


_POSITIVE_BOOKING_TERMS = [
    "yes", "yeah", "yep", "yup", "sure", "absolutely", "definitely",
    "sounds good", "sounds great", "that sounds good", "that sounds great",
    "let's do it", "lets do it", "let's go", "lets go",
    "i'd love that", "id love that", "i would love that",
    "that would be great", "that would be amazing",
    "ok", "okay", "of course", "for sure", "great idea", "love that",
    "i'm ready", "im ready", "i am ready", "ready",
    "sign me up", "book", "schedule",
]


def _user_confirmed_booking(user_message: str) -> bool:
    """Returns True if the user's message is a positive response to the buy-in question."""
    msg = user_message.lower().strip()
    return any(term in msg for term in _POSITIVE_BOOKING_TERMS)


def _find_question_for_dim(dim: str, questions: list[str]) -> str | None:
    keywords = _DIM_QUESTION_KEYWORDS.get(dim, [])
    for q in questions:
        q_lower = q.lower()
        if any(kw in q_lower for kw in keywords):
            return q
    return questions[0] if questions else None


def _select_question(prior_tags: dict, questions: list[str]) -> str | None:
    """Return a question for the highest-priority dimension that's still at its default value."""
    if not questions:
        return None
    for dim in _DIM_PRIORITY:
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
) -> tuple[tuple[str, str] | None, tuple[str, str] | None, bool, bool]:
    """
    Single cheap LLM call that classifies the conversation's semantic context.
    Returns (matched_pattern | None, matched_objection | None, authority_useful: bool, low_intent: bool).
    """
    # Build recent conversation context (last 6 turns + current message)
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
        "You are a conversation classifier. Analyze the following conversation and return a JSON object.\n\n"
        f"Conversation:\n{convo}\n\n"
        f"Available scenarios (return the index, or -1 if none clearly applies):\n{scenario_list}\n\n"
        f"Available objections (return the index, or -1 if none clearly applies):\n{objection_list}\n\n"
        "IMPORTANT — objections are ONLY about the coaching program or service itself: "
        "e.g. the cost is too high, feeling overwhelmed by too much health information, "
        "or scepticism that coaching will work. "
        "Emotional distress about a diagnosis or test results is NOT an objection — return -1 for those.\n\n"
        "Should authority or credentials be mentioned? "
        "Return true ONLY IF the user is explicitly questioning whether this approach works, "
        "asking for proof or track record, or expressing direct scepticism about the program. "
        "Return false for emotional sharing, general questions, or anything else. "
        "When in doubt, return false.\n\n"
        "Is the user's intent vague or exploratory — just browsing, asking what this is about, or not sharing anything personal yet? (true/false)\n\n"
        'Return only valid JSON: {"scenario": <integer>, "objection": <integer>, "authority_useful": <boolean>, "low_intent": <boolean>}'
    )

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": classifier_prompt}],
            temperature=0,
            max_tokens=60,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content or "{}")
        scenario_idx  = int(data.get("scenario", -1))
        objection_idx = int(data.get("objection", -1))
        authority_useful = bool(data.get("authority_useful", False))
        low_intent = bool(data.get("low_intent", False))

        matched_pattern   = pattern_pairs[scenario_idx]   if 0 <= scenario_idx  < len(pattern_pairs)   else None
        matched_objection = objection_pairs[objection_idx] if 0 <= objection_idx < len(objection_pairs) else None

        logger.debug(
            "Classifier → scenario=%d (%s), objection=%d (%s), authority=%s, low_intent=%s",
            scenario_idx,  matched_pattern[0]   if matched_pattern   else "none",
            objection_idx, matched_objection[0] if matched_objection else "none",
            authority_useful, low_intent,
        )
        return matched_pattern, matched_objection, authority_useful, low_intent

    except Exception as exc:
        logger.warning("Classifier call failed (%s) — skipping semantic context injection", exc)
        return None, None, False, False


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
) -> RouteContext:
    """
    Builds a RouteContext that tells the prompt assembler exactly what to inject
    for this specific conversation turn.

    Booking two-step:
      Phase A — score crosses threshold, buy-in not yet asked → booking_ask_confirmation=True
      Phase B — buy-in already asked, user confirmed positively → booking_fires_now=True
    """
    is_first = len(history) == 0

    # Determine booking phase
    score_qualifies = threshold > 0 and current_score >= threshold
    booking_fires_now = False
    booking_ask_confirmation = False

    if not already_sent:
        if already_asked and _user_confirmed_booking(user_message):
            booking_fires_now = True
        elif score_qualifies and not already_asked:
            booking_ask_confirmation = True

    # ── Part A: Deterministic ─────────────────────────────────────────────────

    # Opening variant — only on the very first message (determined by database history)
    opening_variant: str | None = None
    if is_first:
        variants = _parse_list(cfg.get("prompt_opening_variants", ""))
        if variants:
            opening_variant = random.choice(variants)

    # Known facts from prior tags + history — injected so the AI never re-asks them
    known_facts = _derive_known_facts(prior_tags, history) if not is_first else None

    # Qualification question — one per turn, for the highest-priority unknown dimension
    question_for_dim = _select_question(
        prior_tags,
        _parse_list(cfg.get("prompt_qualification_questions", "")),
    )

    # CTA line — when score approaches booking threshold (but not when ask/fire is happening)
    cta_line: str | None = None
    if threshold > 0 and current_score >= int(threshold * 0.75) and not booking_fires_now and not booking_ask_confirmation:
        cta_options = _parse_list(cfg.get("prompt_cta_transitions", ""))
        if cta_options:
            cta_line = random.choice(cta_options)

    # ── Part B: LLM Classifier ────────────────────────────────────────────────
    # Skip entirely on turn 1 — the opening variant is the only injection needed.
    # Running the classifier on a single opening message produces false positives
    # (e.g. "I'm devastated" wrongly triggers the overwhelm objection handler).

    matched_pattern: tuple[str, str] | None   = None
    matched_objection: tuple[str, str] | None = None
    authority_phrase: str | None              = None
    low_intent: bool                          = False

    # Deterministic high-emotion detection — keyword check on the raw user message
    msg_lower = user_message.lower()
    suppress_question: bool = any(term in msg_lower for term in _HIGH_EMOTION_USER_TERMS)

    # High-emotion first message: drop the opening variant — acknowledge the emotion directly
    if suppress_question:
        opening_variant = None

    if not is_first:
        pattern_pairs     = _parse_labeled_list(cfg.get("prompt_pattern_responses", ""))
        objection_pairs   = _parse_labeled_list(cfg.get("prompt_objection_handling", ""))
        authority_phrases = _parse_list(cfg.get("prompt_authority_proof", ""))

        if pattern_pairs or objection_pairs or authority_phrases:
            matched_pattern, matched_objection, authority_useful, low_intent = await _run_classifier(
                user_message=user_message,
                history=history,
                pattern_pairs=pattern_pairs,
                objection_pairs=objection_pairs,
                openai_client=openai_client,
            )
            if authority_useful and authority_phrases:
                authority_phrase = random.choice(authority_phrases)

        # Also suppress if the classifier matched a high-emotion pattern label
        if not suppress_question and matched_pattern:
            label_lower = matched_pattern[0].lower()
            if any(kw in label_lower for kw in _HIGH_EMOTION_KEYWORDS):
                suppress_question = True

    # Also suppress qualification question on turn 1 — the opening variant
    # already ends with a question; stacking another creates the "multiple questions" problem.
    if is_first:
        question_for_dim = None

    booking_url = cfg.get("booking_link", "").strip() if booking_fires_now else ""
    # Can't fire booking link without a URL configured — treat as not firing, fall back to ask
    if booking_fires_now and not booking_url:
        booking_fires_now = False
        if not already_asked:
            booking_ask_confirmation = True

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
    )
