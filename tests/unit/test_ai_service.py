import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.ai import (
    build_system_prompt,
    parse_score_from_response,
    generate_reply,
    HARD_NO_FALLBACK,
)


def test_system_prompt_contains_hard_nos(mock_cfg):
    prompt = build_system_prompt(mock_cfg)
    assert "competitor" in prompt
    assert "other clinic" in prompt


def test_system_prompt_contains_base_prompt(mock_cfg):
    prompt = build_system_prompt(mock_cfg)
    assert "fertility" in prompt.lower()


def test_system_prompt_contains_scoring_instructions(mock_cfg):
    prompt = build_system_prompt(mock_cfg)
    assert "[SCORE:" in prompt


def test_system_prompt_default_when_empty():
    prompt = build_system_prompt({})
    assert "fertility" in prompt.lower()
    assert "[SCORE:" in prompt


def test_parse_score_strips_marker():
    clean, delta = parse_score_from_response("Great question! Let me help you.\n[SCORE:10]")
    assert clean == "Great question! Let me help you."
    assert delta == 10


def test_parse_score_negative_delta():
    clean, delta = parse_score_from_response("I understand your concerns.\n[SCORE:-5]")
    assert delta == -5
    assert "[SCORE:" not in clean


def test_parse_score_no_marker_defaults_zero():
    clean, delta = parse_score_from_response("Just a normal reply.")
    assert delta == 0
    assert clean == "Just a normal reply."


def test_parse_score_marker_in_middle_not_parsed():
    text = "Here is [SCORE:10] in the middle.\nFinal line."
    clean, delta = parse_score_from_response(text)
    assert delta == 0
    assert "[SCORE:10]" not in clean  # stripped but delta=0


def test_parse_score_malformed_number():
    clean, delta = parse_score_from_response("Reply.\n[SCORE:abc]")
    assert delta == 0


@pytest.mark.asyncio
async def test_generate_reply_returns_clean_reply_and_delta(mock_cfg, mock_openai_client):
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="You're in the right place!\n[SCORE:8]"))]
    )
    clean, delta = await generate_reply(
        user_message="I'm interested in fertility treatments.",
        history=[],
        cfg=mock_cfg,
        user_first_name="Sarah",
        openai_client=mock_openai_client,
    )
    assert delta == 8
    assert "[SCORE:" not in clean
    assert "You're in the right place!" in clean


@pytest.mark.asyncio
async def test_generate_reply_hard_no_in_ai_response_returns_fallback(mock_cfg, mock_openai_client):
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="You should visit our competitor instead.\n[SCORE:5]"))]
    )
    clean, delta = await generate_reply(
        user_message="Tell me about options.",
        history=[],
        cfg=mock_cfg,
        user_first_name=None,
        openai_client=mock_openai_client,
    )
    assert clean == HARD_NO_FALLBACK
    assert delta == 0


@pytest.mark.asyncio
async def test_generate_reply_builds_history_in_messages_format(mock_cfg, mock_openai_client):
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Of course!\n[SCORE:3]"))]
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
    # History turn should be included
    contents = [m["content"] for m in messages]
    assert any("trying for a year" in c for c in contents)
