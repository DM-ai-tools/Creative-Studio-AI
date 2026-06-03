import logging
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.services.meta.client import MetaGraphClient

logger = logging.getLogger(__name__)


class MetaService:
    def __init__(self) -> None:
        self._client = MetaGraphClient()

    def status(self) -> dict[str, Any]:
        return {
            "configured": self._client.is_configured,
            "app_id": settings.META_APP_ID or None,
            "ad_account_id": settings.META_AD_ACCOUNT_ID or None,
            "graph_api_version": settings.META_GRAPH_API_VERSION,
            "auth_mode": "static_token",
        }

    async def verify(self) -> dict[str, Any]:
        if not self._client.is_configured:
            return {
                **self.status(),
                "connected": False,
                "message": "Meta credentials are missing from environment configuration",
            }

        try:
            profile = await self._client.verify_credentials()
            ad_accounts = await self._client.get_ad_accounts()
            return {
                **self.status(),
                "connected": True,
                "profile": profile,
                "ad_accounts": ad_accounts,
                "message": "Meta credentials validated",
            }
        except Exception as exc:
            logger.exception("Meta credential verification failed")
            return {
                **self.status(),
                "connected": False,
                "message": str(exc),
            }

    async def export_variants(
        self,
        *,
        tenant_id: UUID,
        variant_ids: list[UUID],
        campaign_name: str,
        ad_set_name: str | None = None,
    ) -> dict[str, Any]:
        verification = await self.verify()
        if not verification.get("connected"):
            raise RuntimeError(verification.get("message", "Meta is not connected"))

        ad_account_id = settings.META_AD_ACCOUNT_ID
        if not ad_account_id and verification.get("ad_accounts"):
            ad_account_id = verification["ad_accounts"][0].get("id")

        logger.info(
            "Meta export queued tenant=%s variants=%s campaign=%s ad_set=%s ad_account=%s",
            tenant_id,
            len(variant_ids),
            campaign_name,
            ad_set_name,
            ad_account_id,
        )

        return {
            "status": "queued",
            "auth_mode": "static_token",
            "campaign_name": campaign_name,
            "ad_set_name": ad_set_name,
            "variant_ids": [str(variant_id) for variant_id in variant_ids],
            "ad_account_id": ad_account_id,
            "message": "Export accepted using configured Meta access token",
        }


meta_service = MetaService()
