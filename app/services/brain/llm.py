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

# USD per token as (input, cached_input, output). Source: OpenAI standard
# pricing, retrieved 2026-08-03. Add a row when adding a model; unknown models
# cost 0 and log once rather than raising mid-turn.
#
# The cached column is why the writer prompt is ordered core-then-mode: that
# prefix is byte-identical across every turn in a mode, and on the larger models
# a cached input token is a TENTH of a fresh one, against a half on 4o-mini. The
# stronger the writer, the more the cache-shaped prompt is worth.
_COSTS = {
    "gpt-4o-mini":  (0.00000015,  0.000000075, 0.0000006),
    "gpt-4o":       (0.0000025,   0.00000125,  0.00001),
    "gpt-4.1":      (0.000002,    0.0000005,   0.000008),
    "gpt-4.1-mini": (0.0000004,   0.0000001,   0.0000016),
    "gpt-5":        (0.00000125,  0.000000125, 0.00001),
    "gpt-5-mini":   (0.00000025,  0.000000025, 0.000002),
}

_warned_models: set[str] = set()


def model_for(role: str, cfg: Optional[dict] = None) -> str:
    """The model for a role, honouring `model_<role>` in app_config."""
    override = ((cfg or {}).get(f"model_{role}") or "").strip()
    return override or _DEFAULT_MODELS.get(role, "gpt-4o-mini")


# Model families that renamed `max_tokens` and refuse a custom temperature.
_NEW_PARAM_FAMILIES = ("gpt-5", "o1", "o3", "o4")


def supports_temperature(model: str) -> bool:
    return not model.startswith(_NEW_PARAM_FAMILIES)


def completion_kwargs(model: str, *, max_tokens: int,
                      temperature: Optional[float] = None) -> dict:
    """Per-model call parameters.

    The GPT-5 family renamed `max_tokens` to `max_completion_tokens` and accepts
    only the default temperature; sending either of the old ones is a hard 400.
    Without this, choosing a stronger writer is not the config change the design
    promises - it is a code change, and it fails on the first message.

    They are also reasoning models, and reasoning tokens are drawn from the SAME
    budget as the reply. At the 500 we allow the writer, gpt-5 spent all 500
    thinking and returned nothing at all - a hard failure, not a short answer. So
    they get `reasoning_effort="minimal"` (measured: 0 reasoning tokens, 171 for
    the reply) plus headroom, because a DM reply is a writing task and thinking
    longer about it buys nothing.

    Note the consequence: on those models the writer runs at the default
    temperature rather than the 0.7 used elsewhere, so variation comes from the
    rotated playbook examples rather than from sampling.
    """
    if model.startswith(_NEW_PARAM_FAMILIES):
        return {
            "max_completion_tokens": max_tokens * 2,
            "reasoning_effort": "minimal",
        }
    kwargs: dict = {"max_tokens": max_tokens}
    if temperature is not None:
        kwargs["temperature"] = temperature
    return kwargs


def usage_of(response, model: str, role: str) -> dict:
    """Normalized usage dict. `role` is kept so a turn's calls stay separable in
    the cost table instead of being blended into one figure."""
    u = getattr(response, "usage", None)
    prompt_tokens = getattr(u, "prompt_tokens", 0) or 0
    completion_tokens = getattr(u, "completion_tokens", 0) or 0
    # Cached prefix tokens are billed at a fraction of the rate. Ignoring them
    # overstates the cost of exactly the design that makes the big prompt
    # affordable, so they are counted separately.
    details = getattr(u, "prompt_tokens_details", None)
    cached_tokens = getattr(details, "cached_tokens", 0) or 0
    cached_tokens = min(cached_tokens, prompt_tokens)
    fresh_tokens = prompt_tokens - cached_tokens

    rates = _COSTS.get(model)
    if rates is None:
        if model not in _warned_models:
            logger.warning("No cost table for model %s; recording 0 cost", model)
            _warned_models.add(model)
        rates = (0.0, 0.0, 0.0)
    return {
        "role": role,
        "ai_model": model,
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "completion_tokens": completion_tokens,
        "token_cost": (fresh_tokens * rates[0]
                       + cached_tokens * rates[1]
                       + completion_tokens * rates[2]),
    }


def combine_usage(*usages: dict) -> dict:
    """Sum usage across a turn's calls, keeping the per-call breakdown in `calls`.

    The totals keep the legacy key names so `save_message` and the existing cost
    columns keep working unchanged.
    """
    out = {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0,
           "token_cost": 0.0, "ai_model": None, "calls": []}
    for u in usages:
        if not u:
            continue
        out["prompt_tokens"] += u.get("prompt_tokens", 0) or 0
        out["cached_tokens"] += u.get("cached_tokens", 0) or 0
        out["completion_tokens"] += u.get("completion_tokens", 0) or 0
        out["token_cost"] += u.get("token_cost", 0.0) or 0.0
        out["ai_model"] = u.get("ai_model") or out["ai_model"]
        # Flatten, never nest. A combined usage carries no `role` of its own, so
        # appending one buries the individual calls inside it and the breakdown
        # this list exists for silently turns into a row labelled None. That is
        # what happened to the writer's regeneration and to the checker panel:
        # 7 of 28 calls were unattributable.
        nested = u.get("calls")
        out["calls"].extend(nested if nested else [u])
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
