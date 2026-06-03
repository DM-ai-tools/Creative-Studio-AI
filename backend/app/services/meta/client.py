import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MetaGraphClient:
    def __init__(self) -> None:
        self._base_url = f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}"

    @property
    def is_configured(self) -> bool:
        return bool(settings.META_ACCESS_TOKEN and settings.META_APP_ID)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.META_ACCESS_TOKEN}"}

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured:
            raise RuntimeError("Meta credentials are not configured")

        url = path if path.startswith("http") else f"{self._base_url}/{path.lstrip('/')}"
        query = dict(params or {})
        if settings.META_ACCESS_TOKEN and "access_token" not in query:
            query.setdefault("access_token", settings.META_ACCESS_TOKEN)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                url,
                params=query,
                json=json,
                headers=self._headers(),
            )
            body = response.json()
            if response.is_error:
                logger.error("Meta Graph API error %s: %s", response.status_code, body)
                message = body.get("error", {}).get("message", "Meta API request failed")
                raise RuntimeError(message)
            return body

    async def verify_credentials(self) -> dict[str, Any]:
        return await self.request("GET", "me", params={"fields": "id,name"})

    async def get_ad_accounts(self) -> list[dict[str, Any]]:
        payload = await self.request("GET", "me/adaccounts", params={"fields": "id,name,account_status"})
        return payload.get("data", [])
