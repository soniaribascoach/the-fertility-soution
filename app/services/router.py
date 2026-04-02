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
    booking_url: str = ""                   # The URL to embed when booking_fires_now is True


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
) -> tuple[tuple[str, str] | None, tuple[str, str] | None, bool]:
    """
    Single cheap LLM call that classifies the conversation's semantic context.
    Returns (matched_pattern | None, matched_objection | None, authority_useful: bool).
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
        "Would including a credibility or authority proof point feel natural in the AI's next reply? (true/false)\n\n"
        'Return only valid JSON: {"scenario": <integer>, "objection": <integer>, "authority_useful": <boolean>}'
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

        matched_pattern   = pattern_pairs[scenario_idx]   if 0 <= scenario_idx  < len(pattern_pairs)   else None
        matched_objection = objection_pairs[objection_idx] if 0 <= objection_idx < len(objection_pairs) else None

        logger.debug(
            "Classifier → scenario=%d (%s), objection=%d (%s), authority=%s",
            scenario_idx,  matched_pattern[0]   if matched_pattern   else "none",
            objection_idx, matched_objection[0] if matched_objection else "none",
            authority_useful,
        )
        return matched_pattern, matched_objection, authority_useful

    except Exception as exc:
        logger.warning("Classifier call failed (%s) — skipping semantic context injection", exc)
        return None, None, False


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
) -> RouteContext:
    """
    Builds a RouteContext that tells the prompt assembler exactly what to inject
    for this specific conversation turn.
    """
    is_first = len(history) == 0
    booking_fires_now = threshold > 0 and current_score >= threshold and not already_sent

    # ── Part A: Deterministic ─────────────────────────────────────────────────

    # Opening variant — only on the very first message
    opening_variant: str | None = None
    if is_first:
        variants = _parse_list(cfg.get("prompt_opening_variants", ""))
        if variants:
            opening_variant = random.choice(variants)

    # Qualification question — one per turn, for the highest-priority unknown dimension
    question_for_dim = _select_question(
        prior_tags,
        _parse_list(cfg.get("prompt_qualification_questions", "")),
    )

    # CTA line — when score approaches booking threshold (but not the turn it actually fires)
    cta_line: str | None = None
    if threshold > 0 and current_score >= int(threshold * 0.75) and not booking_fires_now:
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

    if not is_first:
        pattern_pairs     = _parse_labeled_list(cfg.get("prompt_pattern_responses", ""))
        objection_pairs   = _parse_labeled_list(cfg.get("prompt_objection_handling", ""))
        authority_phrases = _parse_list(cfg.get("prompt_authority_proof", ""))

        if pattern_pairs or objection_pairs or authority_phrases:
            matched_pattern, matched_objection, authority_useful = await _run_classifier(
                user_message=user_message,
                history=history,
                pattern_pairs=pattern_pairs,
                objection_pairs=objection_pairs,
                openai_client=openai_client,
            )
            if authority_useful and authority_phrases:
                authority_phrase = random.choice(authority_phrases)

    # Also suppress qualification question on turn 1 — the opening variant
    # already ends with a question; stacking another creates the "multiple questions" problem.
    if is_first:
        question_for_dim = None

    booking_url = cfg.get("booking_link", "").strip() if booking_fires_now else ""
    # Can't fire booking link without a URL configured — treat as not firing
    if not booking_url:
        booking_fires_now = False

    return RouteContext(
        is_first_message=is_first,
        opening_variant=opening_variant,
        matched_pattern=matched_pattern,
        matched_objection=matched_objection,
        question_for_dim=question_for_dim,
        authority_phrase=authority_phrase,
        cta_line=cta_line,
        booking_fires_now=booking_fires_now,
        booking_url=booking_url,
    )
