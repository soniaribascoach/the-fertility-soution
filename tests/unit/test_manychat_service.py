import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.manychat import ManyChatService


def make_response(status_code: int) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = (200 <= status_code < 300)
    return resp


@pytest.fixture
def mock_http_client():
    client = MagicMock(spec=httpx.AsyncClient)
    client.post = AsyncMock()
    return client


@pytest.fixture
def mc_svc(mock_http_client):
    return ManyChatService(api_token="test-token-123", http_client=mock_http_client)


@pytest.mark.asyncio
async def test_send_text_message_200_returns_true(mc_svc, mock_http_client):
    mock_http_client.post.return_value = make_response(200)
    result = await mc_svc.send_text_message("sub_123", "Hello!")
    assert result is True


@pytest.mark.asyncio
async def test_send_text_message_non_2xx_returns_false(mc_svc, mock_http_client):
    mock_http_client.post.return_value = make_response(400)
    result = await mc_svc.send_text_message("sub_123", "Hello!")
    assert result is False


@pytest.mark.asyncio
async def test_send_text_message_500_returns_false(mc_svc, mock_http_client):
    mock_http_client.post.return_value = make_response(500)
    result = await mc_svc.send_text_message("sub_123", "Hello!")
    assert result is False


@pytest.mark.asyncio
async def test_bearer_token_in_request_header(mc_svc, mock_http_client):
    mock_http_client.post.return_value = make_response(200)
    await mc_svc.send_text_message("sub_123", "Test")

    call_kwargs = mock_http_client.post.call_args.kwargs
    assert "Authorization" in call_kwargs["headers"]
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-token-123"


@pytest.mark.asyncio
async def test_send_booking_link_includes_url_in_body(mc_svc, mock_http_client):
    mock_http_client.post.return_value = make_response(200)
    await mc_svc.send_booking_link("sub_456", "https://example.com/book", "Sarah")

    call_kwargs = mock_http_client.post.call_args.kwargs
    body = call_kwargs["json"]
    messages = body["data"]["content"]["messages"]
    assert any("https://example.com/book" in m.get("text", "") for m in messages)


@pytest.mark.asyncio
async def test_send_booking_link_includes_first_name(mc_svc, mock_http_client):
    mock_http_client.post.return_value = make_response(200)
    await mc_svc.send_booking_link("sub_456", "https://example.com/book", "Emma")

    call_kwargs = mock_http_client.post.call_args.kwargs
    body = call_kwargs["json"]
    messages = body["data"]["content"]["messages"]
    assert any("Emma" in m.get("text", "") for m in messages)


@pytest.mark.asyncio
async def test_send_booking_link_fallback_name_when_none(mc_svc, mock_http_client):
    mock_http_client.post.return_value = make_response(200)
    await mc_svc.send_booking_link("sub_456", "https://example.com/book", None)
    # Should not raise; uses "there" as fallback
    assert mock_http_client.post.called


@pytest.mark.asyncio
async def test_network_error_returns_false(mc_svc, mock_http_client):
    mock_http_client.post.side_effect = httpx.RequestError("Connection failed")
    result = await mc_svc.send_text_message("sub_123", "Hello!")
    assert result is False
