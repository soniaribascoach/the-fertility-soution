import logging

import httpx

logger = logging.getLogger(__name__)

# Tags for each dimension, ordered from lowest to highest value
_DIMENSION_TAGS = {
    "ttc": ["ttc_0-6mo", "ttc_6-12mo", "ttc_1-2yr", "ttc_2yr+"],
    "diagnosis": ["diagnosis_none", "diagnosis_suspected", "diagnosis_confirmed"],
    "urgency": ["urgency_low", "urgency_medium", "urgency_high"],
    "readiness": ["readiness_exploring", "readiness_considering", "readiness_ready"],
    "fit": ["fit_low", "fit_medium", "fit_high"],
}


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

    async def add_tag(self, subscriber_id: str, tag_name: str) -> bool:
        """Adds a tag to a ManyChat subscriber."""
        payload = {"subscriber_id": subscriber_id, "tag_name": tag_name}
        try:
            resp = await self._client.post(
                f"{self.BASE_URL}/fb/subscriber/addTag",
                headers=self._headers(),
                json=payload,
            )
            return resp.is_success
        except httpx.RequestError:
            logger.warning("Failed to add tag %s for subscriber %s", tag_name, subscriber_id)
            return False

    async def remove_tag(self, subscriber_id: str, tag_name: str) -> bool:
        """Removes a tag from a ManyChat subscriber."""
        payload = {"subscriber_id": subscriber_id, "tag_name": tag_name}
        try:
            resp = await self._client.post(
                f"{self.BASE_URL}/fb/subscriber/removeTag",
                headers=self._headers(),
                json=payload,
            )
            return resp.is_success
        except httpx.RequestError:
            logger.warning("Failed to remove tag %s for subscriber %s", tag_name, subscriber_id)
            return False

    async def update_contact_tags(
        self,
        subscriber_id: str,
        old_tags: dict[str, str],
        new_tags: dict[str, str],
    ) -> None:
        """
        Diffs old and new tags per dimension. For each dimension where the value
        has changed, removes the old tag and adds the new tag.
        """
        for dimension in _DIMENSION_TAGS:
            old_tag = old_tags.get(dimension)
            new_tag = new_tags.get(dimension)
            if new_tag and new_tag != old_tag:
                if old_tag:
                    await self.remove_tag(subscriber_id, old_tag)
                await self.add_tag(subscriber_id, new_tag)
