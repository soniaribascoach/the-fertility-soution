import httpx


class ManyChatService:
    BASE_URL = "https://api.manychat.com"

    def __init__(self, api_token: str, http_client: httpx.AsyncClient):
        self._token = api_token
        self._client = http_client

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def send_text_message(self, subscriber_id: str, text: str) -> bool:
        payload = {
            "subscriber_id": subscriber_id,
            "data": {
                "version": "v2",
                "content": {
                    "messages": [{"type": "text", "text": text}],
                },
            },
        }
        try:
            resp = await self._client.post(
                f"{self.BASE_URL}/fb/sending/sendContent",
                headers=self._headers(),
                json=payload,
            )
            return resp.is_success
        except httpx.RequestError:
            return False

    async def send_booking_link(
        self, subscriber_id: str, url: str, first_name: str | None = None
    ) -> bool:
        name = first_name or "there"
        text = (
            f"Hi {name}! Based on our conversation, I think you're ready to take the next step. "
            f"Here's your booking link to schedule a free consultation: {url} 🌸\n\n"
            "I can't wait to support you on this journey!"
        )
        return await self.send_text_message(subscriber_id, text)
