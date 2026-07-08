"""Live extractor tests (Step 3) — real OpenAI calls, no mocks.

Run with: pytest -m live tests/brain/test_extractor.py
"""
import pytest

from app.services.brain.constants import empty_lead_state
from app.services.brain.extractor import extract, non_null_deltas

pytestmark = pytest.mark.live


def _slots():
    return empty_lead_state()["slots"]


async def test_extracts_age_duration_and_treatment(openai_client):
    history = [
        {"role": "assistant", "content": "How long have you been trying, and what have you already tried?"},
        {"role": "user", "content": "I'm 39, we've been trying for 2 years and we did 2 failed IUIs."},
    ]
    result, usage = await extract(openai_client, history, _slots())
    deltas = non_null_deltas(result.slot_deltas)
    assert result.slot_deltas.age == 39
    assert "2 year" in (result.slot_deltas.trying_duration or "").lower()
    assert "iui" in (result.slot_deltas.what_tried or "").lower()
    assert result.intent == "shares_situation"
    assert usage["token_cost"] > 0


async def test_classifies_price_question_and_extracts_nothing(openai_client):
    history = [{"role": "user", "content": "How much does your program cost?"}]
    result, _ = await extract(openai_client, history, _slots())
    assert result.intent == "asks_price"
    # A bare price question reveals no situation facts.
    assert result.slot_deltas.age is None
    assert result.slot_deltas.trying_duration is None


async def test_detects_blocked_tubes_oos(openai_client):
    history = [{"role": "user", "content": "My doctor said both my fallopian tubes are blocked."}]
    result, _ = await extract(openai_client, history, _slots())
    assert result.oos_signal == "blocked_tubes"
    assert result.slot_deltas.tubes_blocked == "both"


async def test_unspecified_blocked_tubes_not_read_as_both(openai_client):
    # Sonia v1.1: "my tubes are blocked" without both/one must NOT be read as
    # both; the controller has to ask which (ASK_BOTH_TUBES).
    history = [{"role": "user", "content": "My doctor said my tubes are blocked."}]
    result, _ = await extract(openai_client, history, _slots())
    assert result.oos_signal == "blocked_tubes"
    assert result.slot_deltas.tubes_blocked in (None, "unspecified")


async def test_detects_no_period_over_12_months(openai_client):
    history = [{"role": "user", "content": "I haven't had a period in 14 months."}]
    result, _ = await extract(openai_client, history, _slots())
    assert result.slot_deltas.no_period_over_year is True


async def test_detects_is_this_ai_takeover(openai_client):
    history = [{"role": "user", "content": "wait, am I talking to a bot right now?"}]
    result, _ = await extract(openai_client, history, _slots())
    assert result.takeover is True


async def test_extracts_priority_score_in_context(openai_client):
    history = [
        {"role": "assistant", "content": "On a scale of 1 to 10, how much of a priority is getting pregnant right now?"},
        {"role": "user", "content": "honestly a 9, it's the most important thing to me"},
    ]
    result, _ = await extract(openai_client, history, _slots())
    assert result.slot_deltas.priority_score == 9


async def test_does_not_invent_unstated_facts(openai_client):
    # A vague opener must not produce hallucinated slots.
    history = [{"role": "user", "content": "hi, I saw your reel and wanted to reach out"}]
    result, _ = await extract(openai_client, history, _slots())
    assert non_null_deltas(result.slot_deltas) == {}
