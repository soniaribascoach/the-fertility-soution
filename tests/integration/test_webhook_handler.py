import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from app.services.webhook import handle_contact
from app.repositories import conversation as conv_repo


@pytest.fixture
def mc_svc():
    svc = MagicMock()
    svc.send_text_message = AsyncMock(return_value=True)
    svc.send_booking_link = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def openai_client():
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock()
    return client


def make_openai_response(text: str):
    return MagicMock(choices=[MagicMock(message=MagicMock(content=text))])


@pytest.mark.asyncio
async def test_happy_path_sends_reply(async_db_session, mock_cfg, mc_svc, openai_client):
    openai_client.chat.completions.create.return_value = make_openai_response(
        "I'm so glad you reached out!\n[SCORE:5]"
    )

    await handle_contact(
        instagram_user_id="user_001",
        user_message="Hi, I'm interested in fertility options.",
        first_name="Sarah",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    mc_svc.send_text_message.assert_awaited_once()
    mc_svc.send_booking_link.assert_not_awaited()


@pytest.mark.asyncio
async def test_booking_link_sent_at_threshold(async_db_session, mock_cfg, mc_svc, openai_client):
    # Score delta pushes over threshold of 70
    openai_client.chat.completions.create.return_value = make_openai_response(
        "You are ready to book!\n[SCORE:70]"
    )

    await handle_contact(
        instagram_user_id="user_002",
        user_message="I'm ready to schedule!",
        first_name="Emma",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    mc_svc.send_booking_link.assert_awaited_once()
    mc_svc.send_text_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_booking_link_not_sent_twice(async_db_session, mock_cfg, mc_svc, openai_client):
    openai_client.chat.completions.create.return_value = make_openai_response(
        "Great! Here's your link.\n[SCORE:70]"
    )

    # First contact — should send booking link
    await handle_contact(
        instagram_user_id="user_003",
        user_message="I'm ready!",
        first_name="Lisa",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )
    assert mc_svc.send_booking_link.await_count == 1

    # Second contact — already sent, should not send again
    await handle_contact(
        instagram_user_id="user_003",
        user_message="I'm still here!",
        first_name="Lisa",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )
    assert mc_svc.send_booking_link.await_count == 1  # still 1, not 2
    assert mc_svc.send_text_message.await_count == 1


@pytest.mark.asyncio
async def test_medical_blocklist_skips_ai(async_db_session, mock_cfg, mc_svc, openai_client):
    await handle_contact(
        instagram_user_id="user_004",
        user_message="What is the right metformin dosage for me?",
        first_name="Anna",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    openai_client.chat.completions.create.assert_not_awaited()
    mc_svc.send_text_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_always_logged(async_db_session, mock_cfg, mc_svc, openai_client):
    """Conversation messages are always saved to DB (tested via repo directly)."""
    openai_client.chat.completions.create.return_value = make_openai_response(
        "Here to help!\n[SCORE:3]"
    )

    await handle_contact(
        instagram_user_id="user_005",
        user_message="Hello there.",
        first_name="Mia",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    history = await conv_repo.get_history(async_db_session, "user_005")
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"


@pytest.mark.asyncio
async def test_score_clamped_to_zero_minimum(async_db_session, mock_cfg, mc_svc, openai_client):
    openai_client.chat.completions.create.return_value = make_openai_response(
        "I hear you.\n[SCORE:-100]"
    )

    await handle_contact(
        instagram_user_id="user_006",
        user_message="I'm frustrated.",
        first_name="Jane",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    score = await conv_repo.get_latest_score(async_db_session, "user_006")
    assert score == 0


@pytest.mark.asyncio
async def test_score_clamped_to_100_maximum(async_db_session, mock_cfg, mc_svc, openai_client):
    openai_client.chat.completions.create.return_value = make_openai_response(
        "Wonderful!\n[SCORE:200]"
    )

    await handle_contact(
        instagram_user_id="user_007",
        user_message="I'm so excited!",
        first_name="Kate",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    score = await conv_repo.get_latest_score(async_db_session, "user_007")
    assert score == 100
