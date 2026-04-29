import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_MANYCHAT_BASE = "https://api.manychat.com"
_SEND_URL = f"{_MANYCHAT_BASE}/fb/sending/sendContent"
_RETRY_DELAYS = [1, 2, 4]


class ManyChatClient:
    def __init__(self, api_token: str) -> None:
        self._token = api_token
        self._client = httpx.AsyncClient(timeout=15.0)

    async def send_message(self, subscriber_id: str, text: str) -> None:
        payload = {
            "subscriber_id": subscriber_id,
            "data": {
                "version": "v2",
                "content": {
                    "messages": [{"type": "text", "text": text}],
                    "actions": [],
                    "quick_replies": [],
                },
            },
            "message_tag": "ACCOUNT_UPDATE",
        }
        headers = {"Authorization": f"Bearer {self._token}"}

        for attempt, delay in enumerate(_RETRY_DELAYS + [None], start=1):
            try:
                response = await self._client.post(
                    _SEND_URL, json=payload, headers=headers
                )
                response.raise_for_status()
                return
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                if delay is None:
                    logger.error(
                        "ManyChat send_message failed after %d attempts for subscriber %s: %s",
                        attempt - 1, subscriber_id, exc,
                    )
                    return
                logger.warning(
                    "ManyChat send_message attempt %d failed (%s), retrying in %ds",
                    attempt, exc, delay,
                )
                await asyncio.sleep(delay)

    async def aclose(self) -> None:
        await self._client.aclose()
