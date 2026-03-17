import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from app.services.webhook import handle_contact
from app.repositories import conversation as conv_repo


VALID_TAG_LINE = "[TAGS: ttc=ttc_1-2yr | diagnosis=diagnosis_confirmed | urgency=urgency_high | readiness=readiness_ready | fit=fit_high]"
CONSERVATIVE_TAG_LINE = "[TAGS: ttc=ttc_0-6mo | diagnosis=diagnosis_none | urgency=urgency_low | readiness=readiness_exploring | fit=fit_low]"
# readiness_ready(40) + urgency_high(20) + fit_high(15) = 75 >= 70 threshold
BOOKING_TAG_LINE = "[TAGS: ttc=ttc_0-6mo | diagnosis=diagnosis_none | urgency=urgency_high | readiness=readiness_ready | fit=fit_high]"


@pytest.fixture
def mc_svc():
    svc = MagicMock()
    svc.send_text_message = AsyncMock(return_value=True)
    svc.send_booking_link = AsyncMock(return_value=True)
    svc.add_tag = AsyncMock(return_value=True)
    svc.remove_tag = AsyncMock(return_value=True)
    svc.update_contact_tags = AsyncMock(return_value=None)
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
        f"I'm so glad you reached out!\n{CONSERVATIVE_TAG_LINE}"
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
    # BOOKING_TAG_LINE produces score >= 70
    openai_client.chat.completions.create.return_value = make_openai_response(
        f"You are ready to book!\n{BOOKING_TAG_LINE}"
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
        f"Great! Here's your link.\n{BOOKING_TAG_LINE}"
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
        f"Here to help!\n{CONSERVATIVE_TAG_LINE}"
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
async def test_tags_applied_to_manychat_on_each_turn(async_db_session, mock_cfg, mc_svc, openai_client):
    openai_client.chat.completions.create.return_value = make_openai_response(
        f"Happy to help!\n{VALID_TAG_LINE}"
    )

    await handle_contact(
        instagram_user_id="user_008",
        user_message="I'm interested in next steps.",
        first_name="Amy",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    mc_svc.update_contact_tags.assert_awaited_once()
    call_args = mc_svc.update_contact_tags.call_args
    assert call_args.args[0] == "user_008"  # subscriber_id
    new_tags = call_args.args[2]
    assert new_tags["readiness"] == "readiness_ready"


@pytest.mark.asyncio
async def test_old_tag_removed_when_dimension_changes(async_db_session, mock_cfg, mc_svc, openai_client):
    """On second turn, if readiness changes, update_contact_tags is called with old and new tags."""
    # First turn: exploring
    openai_client.chat.completions.create.return_value = make_openai_response(
        f"Great start!\n{CONSERVATIVE_TAG_LINE}"
    )
    await handle_contact(
        instagram_user_id="user_009",
        user_message="Just browsing.",
        first_name="Beth",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    # Second turn: now readiness is ready
    openai_client.chat.completions.create.return_value = make_openai_response(
        f"Let's get you booked!\n{VALID_TAG_LINE}"
    )
    mc_svc.update_contact_tags.reset_mock()
    await handle_contact(
        instagram_user_id="user_009",
        user_message="I want to book now!",
        first_name="Beth",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    mc_svc.update_contact_tags.assert_awaited_once()
    call_args = mc_svc.update_contact_tags.call_args
    old_tags = call_args.args[1]
    new_tags = call_args.args[2]
    assert old_tags["readiness"] == "readiness_exploring"
    assert new_tags["readiness"] == "readiness_ready"


@pytest.mark.asyncio
async def test_score_stored_in_db(async_db_session, mock_cfg, mc_svc, openai_client):
    openai_client.chat.completions.create.return_value = make_openai_response(
        f"I hear you.\n{CONSERVATIVE_TAG_LINE}"
    )

    await handle_contact(
        instagram_user_id="user_010",
        user_message="I'm frustrated.",
        first_name="Jane",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    score = await conv_repo.get_latest_score(async_db_session, "user_010")
    assert score == 0  # all conservative tags = 0


@pytest.mark.asyncio
async def test_tags_stored_in_db(async_db_session, mock_cfg, mc_svc, openai_client):
    openai_client.chat.completions.create.return_value = make_openai_response(
        f"Wonderful!\n{VALID_TAG_LINE}"
    )

    await handle_contact(
        instagram_user_id="user_011",
        user_message="I'm so excited!",
        first_name="Kate",
        db=async_db_session,
        cfg=mock_cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    tags = await conv_repo.get_latest_tags(async_db_session, "user_011")
    assert tags["readiness"] == "readiness_ready"
    assert tags["ttc"] == "ttc_1-2yr"
