import pytest
from app.repositories import conversation as conv_repo


@pytest.mark.asyncio
async def test_save_and_get_history_order(async_db_session):
    await conv_repo.save_message(async_db_session, "user_A", "user", "First message")
    await conv_repo.save_message(async_db_session, "user_A", "assistant", "First reply")
    await conv_repo.save_message(async_db_session, "user_A", "user", "Second message")

    history = await conv_repo.get_history(async_db_session, "user_A")
    assert len(history) == 3
    assert history[0].content == "First message"
    assert history[1].content == "First reply"
    assert history[2].content == "Second message"


@pytest.mark.asyncio
async def test_get_history_limit(async_db_session):
    for i in range(25):
        await conv_repo.save_message(async_db_session, "user_B", "user", f"Message {i}")

    history = await conv_repo.get_history(async_db_session, "user_B", limit=20)
    assert len(history) == 20
    # Should return the 20 most recent (oldest first)
    assert history[-1].content == "Message 24"


@pytest.mark.asyncio
async def test_get_history_only_for_user(async_db_session):
    await conv_repo.save_message(async_db_session, "user_C", "user", "User C message")
    await conv_repo.save_message(async_db_session, "user_D", "user", "User D message")

    history_c = await conv_repo.get_history(async_db_session, "user_C")
    assert all(r.instagram_user_id == "user_C" for r in history_c)
    assert len(history_c) == 1


@pytest.mark.asyncio
async def test_get_latest_score_returns_most_recent(async_db_session):
    await conv_repo.save_message(async_db_session, "user_E", "assistant", "Reply 1", lead_score=20)
    await conv_repo.save_message(async_db_session, "user_E", "assistant", "Reply 2", lead_score=45)

    score = await conv_repo.get_latest_score(async_db_session, "user_E")
    assert score == 45


@pytest.mark.asyncio
async def test_get_latest_score_no_rows_returns_zero(async_db_session):
    score = await conv_repo.get_latest_score(async_db_session, "user_unknown")
    assert score == 0


@pytest.mark.asyncio
async def test_get_latest_score_skips_null_scores(async_db_session):
    await conv_repo.save_message(async_db_session, "user_F", "user", "No score row")
    await conv_repo.save_message(async_db_session, "user_F", "assistant", "Has score", lead_score=30)

    score = await conv_repo.get_latest_score(async_db_session, "user_F")
    assert score == 30


@pytest.mark.asyncio
async def test_has_received_booking_link_false_initially(async_db_session):
    result = await conv_repo.has_received_booking_link(async_db_session, "user_G")
    assert result is False


@pytest.mark.asyncio
async def test_has_received_booking_link_detected(async_db_session):
    await conv_repo.save_message(
        async_db_session, "user_H", "assistant", "Here is your link. [BOOKING_SENT]", lead_score=80
    )
    result = await conv_repo.has_received_booking_link(async_db_session, "user_H")
    assert result is True


@pytest.mark.asyncio
async def test_has_received_booking_link_not_triggered_by_user_message(async_db_session):
    # Only assistant messages with [BOOKING_SENT] should count
    await conv_repo.save_message(
        async_db_session, "user_I", "user", "Please send me the [BOOKING_SENT] thing"
    )
    result = await conv_repo.has_received_booking_link(async_db_session, "user_I")
    assert result is False
