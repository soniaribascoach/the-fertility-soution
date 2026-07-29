"""Shared OpenAI plumbing for the brain: model selection, cost accounting, retries.

Model names and per-token costs used to be copy-pasted into every module that made
a call (extractor, voice, ai_pipeline), so switching models meant a code change in
three places and the two calls of a turn were indistinguishable in the cost column.
Here they are one table, overridable per-role from `app_config` with no deploy.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Per-role defaults. Override at runtime with the app_config keys below, e.g.
# `model_writer=gpt-4o` — the client can change a model without a deploy.
_DEFAULT_MODELS = {
    "classifier": "gpt-4o-mini",
    "writer": "gpt-4o-mini",
    "checker": "gpt-4o-mini",
}

# USD per token, by model. Add a row when adding a model; unknown models cost 0
# and log once rather than raising mid-turn.
_COSTS = {
    "gpt-4o-mini": (0.00000015, 0.0000006),
    "gpt-4o": (0.0000025, 0.00001),
}

_warned_models: set[str] = set()


def model_for(role: str, cfg: Optional[dict] = None) -> str:
    """The model for a role, honouring `model_<role>` in app_config."""
    override = ((cfg or {}).get(f"model_{role}") or "").strip()
    return override or _DEFAULT_MODELS.get(role, "gpt-4o-mini")


def usage_of(response, model: str, role: str) -> dict:
    """Normalized usage dict. `role` is kept so a turn's calls stay separable in
    the cost table instead of being blended into one figure."""
    u = getattr(response, "usage", None)
    prompt_tokens = getattr(u, "prompt_tokens", 0) or 0
    completion_tokens = getattr(u, "completion_tokens", 0) or 0
    rates = _COSTS.get(model)
    if rates is None:
        if model not in _warned_models:
            logger.warning("No cost table for model %s; recording 0 cost", model)
            _warned_models.add(model)
        rates = (0.0, 0.0)
    return {
        "role": role,
        "ai_model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "token_cost": prompt_tokens * rates[0] + completion_tokens * rates[1],
    }


def combine_usage(*usages: dict) -> dict:
    """Sum usage across a turn's calls, keeping the per-call breakdown in `calls`.

    The totals keep the legacy key names so `save_message` and the existing cost
    columns keep working unchanged.
    """
    out = {"prompt_tokens": 0, "completion_tokens": 0, "token_cost": 0.0,
           "ai_model": None, "calls": []}
    for u in usages:
        if not u:
            continue
        out["prompt_tokens"] += u.get("prompt_tokens", 0) or 0
        out["completion_tokens"] += u.get("completion_tokens", 0) or 0
        out["token_cost"] += u.get("token_cost", 0.0) or 0.0
        out["ai_model"] = u.get("ai_model") or out["ai_model"]
        out["calls"].append(u)
    return out


async def with_retry(coro_factory, *, attempts: int = 3, base_delay: float = 0.5,
                     what: str = "llm call"):
    """Retry a transient API failure with exponential backoff.

    Without this, a single API blip raises out of `run_turn` into the worker's bare
    except, the batch is never marked processed, and the poller retries it forever.
    """
    last: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001 - re-raised below
            last = exc
            if attempt == attempts - 1:
                break
            delay = base_delay * (2 ** attempt)
            logger.warning("%s failed (attempt %d/%d): %s; retrying in %.1fs",
                           what, attempt + 1, attempts, exc, delay)
            await asyncio.sleep(delay)
    raise last  # type: ignore[misc]
