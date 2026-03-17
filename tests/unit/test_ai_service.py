import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.ai import (
    build_system_prompt,
    parse_tags_from_response,
    compute_score,
    generate_reply,
)

VALID_TAG_LINE = "[TAGS: ttc=ttc_1-2yr | diagnosis=diagnosis_confirmed | urgency=urgency_high | readiness=readiness_ready | fit=fit_high]"
CONSERVATIVE_TAG_LINE = "[TAGS: ttc=ttc_0-6mo | diagnosis=diagnosis_none | urgency=urgency_low | readiness=readiness_exploring | fit=fit_low]"


def test_system_prompt_contains_about_section(mock_cfg):
    prompt = build_system_prompt(mock_cfg)
    assert "## About the Business" in prompt
    assert "fertility coaching clinic" in prompt.lower()


def test_system_prompt_contains_services_section(mock_cfg):
    prompt = build_system_prompt(mock_cfg)
    assert "## Service Offerings" in prompt


def test_system_prompt_contains_tone_section(mock_cfg):
    prompt = build_system_prompt(mock_cfg)
    assert "## Conversation & Tone" in prompt


def test_system_prompt_contains_tagging_instructions(mock_cfg):
    prompt = build_system_prompt(mock_cfg)
    assert "[TAGS:" in prompt


def test_system_prompt_default_when_empty():
    prompt = build_system_prompt({})
    assert "fertility" in prompt.lower()
    assert "[TAGS:" in prompt


def test_system_prompt_contains_plain_text_instruction():
    prompt = build_system_prompt({})
    assert "plain text" in prompt.lower()


def test_parse_tags_strips_marker():
    clean, tags = parse_tags_from_response(f"Great question!\n{VALID_TAG_LINE}")
    assert clean == "Great question!"
    assert tags["readiness"] == "readiness_ready"


def test_parse_tags_no_marker_returns_empty():
    clean, tags = parse_tags_from_response("Just a normal reply.")
    assert tags == {}
    assert clean == "Just a normal reply."


def test_parse_tags_marker_in_middle_not_parsed():
    text = f"Here is {VALID_TAG_LINE} in the middle.\nFinal line."
    clean, tags = parse_tags_from_response(text)
    assert tags == {}
    assert "[TAGS:" not in clean  # stripped but tags={}


def test_compute_score_max():
    tags = {
        "ttc": "ttc_2yr+",
        "diagnosis": "diagnosis_confirmed",
        "urgency": "urgency_high",
        "readiness": "readiness_ready",
        "fit": "fit_high",
    }
    assert compute_score(tags) == 100


def test_compute_score_zero():
    tags = {
        "ttc": "ttc_0-6mo",
        "diagnosis": "diagnosis_none",
        "urgency": "urgency_low",
        "readiness": "readiness_exploring",
        "fit": "fit_low",
    }
    assert compute_score(tags) == 0


def test_compute_score_readiness_ready_alone():
    tags = {
        "ttc": "ttc_0-6mo",
        "diagnosis": "diagnosis_none",
        "urgency": "urgency_low",
        "readiness": "readiness_ready",
        "fit": "fit_low",
    }
    assert compute_score(tags) == 40


def test_compute_score_booking_trigger_combination():
    # readiness_ready(40) + fit_high(15) + urgency_high(20) = 75
    tags = {
        "ttc": "ttc_0-6mo",
        "diagnosis": "diagnosis_none",
        "urgency": "urgency_high",
        "readiness": "readiness_ready",
        "fit": "fit_high",
    }
    assert compute_score(tags) >= 70


def test_compute_score_empty_tags_returns_zero():
    assert compute_score({}) == 0


@pytest.mark.asyncio
async def test_generate_reply_returns_clean_reply_and_tags(mock_cfg, mock_openai_client):
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=f"You're in the right place!\n{VALID_TAG_LINE}"))]
    )
    clean, tags, booking_link_used = await generate_reply(
        user_message="I'm interested in fertility treatments.",
        history=[],
        cfg=mock_cfg,
        user_first_name="Sarah",
        openai_client=mock_openai_client,
    )
    assert tags["readiness"] == "readiness_ready"
    assert "[TAGS:" not in clean
    assert "You're in the right place!" in clean
    assert booking_link_used is False


@pytest.mark.asyncio
async def test_generate_reply_builds_history_in_messages_format(mock_cfg, mock_openai_client):
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=f"Of course!\n{CONSERVATIVE_TAG_LINE}"))]
    )

    history_turn = MagicMock()
    history_turn.role = "user"
    history_turn.content = "I have been trying for a year."

    await generate_reply(
        user_message="What should I do?",
        history=[history_turn],
        cfg=mock_cfg,
        user_first_name="Emma",
        openai_client=mock_openai_client,
    )

    call_args = mock_openai_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    roles = [m["role"] for m in messages]
    assert "system" in roles
    assert "user" in roles
    contents = [m["content"] for m in messages]
    assert any("trying for a year" in c for c in contents)
