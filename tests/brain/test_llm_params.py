"""Per-model call parameters.

Choosing a stronger writer is supposed to be one field in AppConfig. It was not:
the GPT-5 family renamed `max_tokens`, refuses a custom temperature, and spends
the reply budget on reasoning tokens. Each of those is a hard 400 or an empty
reply on the first real message, so all three are pinned here.
"""
import pytest

from app.services.brain.llm import _COSTS, completion_kwargs, supports_temperature, usage_of

OLD = ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini"]
NEW = ["gpt-5", "gpt-5-mini", "o1", "o3-mini"]


@pytest.mark.parametrize("model", OLD)
def test_established_models_keep_max_tokens_and_temperature(model):
    kwargs = completion_kwargs(model, max_tokens=500, temperature=0.7)
    assert kwargs == {"max_tokens": 500, "temperature": 0.7}
    assert supports_temperature(model)


@pytest.mark.parametrize("model", NEW)
def test_reasoning_models_get_renamed_param_and_no_temperature(model):
    kwargs = completion_kwargs(model, max_tokens=500, temperature=0.7)
    assert "max_tokens" not in kwargs, "sending max_tokens to this family is a 400"
    assert "temperature" not in kwargs, "only the default temperature is accepted"
    assert kwargs["max_completion_tokens"] >= 500
    assert not supports_temperature(model)


@pytest.mark.parametrize("model", NEW)
def test_reasoning_models_get_headroom_and_minimal_effort(model):
    """Reasoning tokens come out of the SAME budget as the reply. At 500, gpt-5
    spent all 500 thinking and returned nothing - a hard failure, not a short
    answer."""
    kwargs = completion_kwargs(model, max_tokens=500, temperature=None)
    assert kwargs["max_completion_tokens"] > 500
    assert kwargs["reasoning_effort"] == "minimal"


def test_temperature_is_omitted_when_not_asked_for():
    assert completion_kwargs("gpt-4o-mini", max_tokens=100) == {"max_tokens": 100}


# --- cost accounting ---------------------------------------------------------

class _Details:
    def __init__(self, cached):
        self.cached_tokens = cached


class _Usage:
    def __init__(self, prompt, completion, cached=0):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.prompt_tokens_details = _Details(cached)


class _Response:
    def __init__(self, usage):
        self.usage = usage


def test_cached_prefix_tokens_are_billed_at_the_cached_rate():
    """The behavior core is byte-identical every turn and caches. Ignoring that
    overstates the cost of the design that makes the large prompt affordable."""
    fresh = usage_of(_Response(_Usage(1000, 100, cached=0)), "gpt-5", "writer")
    cached = usage_of(_Response(_Usage(1000, 100, cached=900)), "gpt-5", "writer")
    assert cached["cached_tokens"] == 900
    assert cached["token_cost"] < fresh["token_cost"]


def test_cost_is_zero_and_survives_an_unknown_model():
    """An unpriced model must not raise mid-conversation."""
    result = usage_of(_Response(_Usage(100, 10)), "some-future-model", "writer")
    assert result["token_cost"] == 0.0


@pytest.mark.parametrize("model", sorted(_COSTS))
def test_every_priced_model_has_three_rates(model):
    rates = _COSTS[model]
    assert len(rates) == 3, "(input, cached_input, output)"
    assert rates[1] <= rates[0], "cached input is never dearer than fresh input"
