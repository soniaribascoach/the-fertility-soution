import logging

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.config import get_all_config
from app.services.prompt_builder import build_system_prompt
from app.services.pricing_classifier import classify_price_asks

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"
_PROMPT_TOKEN_COST = 0.00000015
_COMPLETION_TOKEN_COST = 0.0000006


async def generate_reply(
    db: AsyncSession,
    openai_client: AsyncOpenAI,
    few_shot_messages: list[dict],
    ig_user_id: str,
    messages: list[dict],
    cfg: dict | None = None,
) -> tuple[str, dict]:
    """Run the full AI pipeline and return (raw_text, usage_info)."""
    if cfg is None:
        cfg = await get_all_config(db)

    blocklist = [p.strip().lower() for p in cfg.get("medical_blocklist", "").split("\n") if p.strip()]
    last_user_msg = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
    ).lower()
    if blocklist and any(phrase in last_user_msg for phrase in blocklist):
        deflection = cfg.get("medical_deflection", "").strip()
        logger.info("Medical blocklist triggered for user %s", ig_user_id)
        return deflection, {}

    price_ask_count = classify_price_asks(messages)
    system_prompt = await build_system_prompt(db, cfg, price_ask_count=price_ask_count)

    response = await openai_client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            *few_shot_messages,
            *messages,
        ],
        max_tokens=500,
        temperature=0.6,
    )

    raw_text = response.choices[0].message.content or ""
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    token_cost = (prompt_tokens * _PROMPT_TOKEN_COST) + (completion_tokens * _COMPLETION_TOKEN_COST)

    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "token_cost": token_cost,
        "ai_model": _MODEL,
    }
    return raw_text, usage
