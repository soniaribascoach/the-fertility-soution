"""Stage 1: read the conversation and report what she actually said.

Deliberately narrow. This call writes nothing a lead will ever see, holds no opinions about tone,
and never decides anything, it extracts facts so that selection and the gates have typed values to
work with. A small model does this reliably precisely because it is the only thing being asked.
"""
import json
import logging
import re

from openai import AsyncOpenAI

from app.services.prompts import build_read_prompt

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

VALID_INTENTS = {
    "new_prospect", "warm_prospect", "existing_client", "former_client",
    "pregnancy_announcement", "birth_announcement", "gratitude", "fertility_question",
    "program_question", "price_question", "ivf_question", "emotional_distress",
    "grief_or_loss", "advice_request", "free_info_request", "collaboration",
    "media_request", "technical_support", "complaint", "not_a_fit", "spam_or_aggression",
}


def _coerce(raw: str) -> dict:
    """Parse the model's JSON, tolerating a code fence or a stray sentence around it."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = _JSON_RE.search(raw or "")
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    logger.warning("Reader returned unparseable JSON: %r", (raw or "")[:300])
    return {}


def normalise(data: dict) -> dict:
    """Force the extraction into the shape the rest of the pipeline expects.

    A reader that invents an intent or returns a string where a list belongs must not be able to
    take the turn down with it; anything unrecognised degrades to the safe default rather than
    raising.
    """
    intent = data.get("intent")
    if intent not in VALID_INTENTS:
        if intent:
            logger.info("Reader returned unknown intent %r, falling back", intent)
        intent = "new_prospect"

    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(t).strip().lower() for t in tags if str(t).strip()][:3]

    language = data.get("language")
    if language not in ("en", "es", "other"):
        language = "en"

    slots = data.get("slots") if isinstance(data.get("slots"), dict) else {}
    flags = data.get("flags") if isinstance(data.get("flags"), dict) else {}

    age = slots.get("age")
    if isinstance(age, str) and age.strip().isdigit():
        slots["age"] = int(age.strip())
    elif age is not None and not isinstance(age, int):
        slots.pop("age", None)

    # `structural` is documented under boundary facts; accept it at either level.
    structural = data.get("structural") or flags.get("structural") or slots.pop("structural", None)
    if structural:
        flags["structural"] = structural

    return {
        "intent": intent,
        "tags": tags,
        "language": language,
        "explicit_question": data.get("explicit_question") or None,
        "emotional_state": data.get("emotional_state") or None,
        "slots": slots,
        "flags": flags,
    }


def _transcript(history: list[dict]) -> str:
    lines = []
    for message in history:
        who = "Lead" if message.get("role") == "user" else "Sonia"
        lines.append(f"{who}: {message.get('content', '')}")
    return "\n".join(lines)


async def read_turn(
    client: AsyncOpenAI,
    history: list[dict],
    *,
    model: str,
) -> tuple[dict, dict]:
    """Return (extraction, usage)."""
    response = await client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": build_read_prompt()},
            {"role": "user", "content": _transcript(history)},
        ],
    )
    raw = response.choices[0].message.content or ""
    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
    }
    return normalise(_coerce(raw)), usage
