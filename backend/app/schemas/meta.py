from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MetaStatusResponse(BaseModel):
  configured: bool
  connected: bool = False
  app_id: str | None = None
  ad_account_id: str | None = None
  graph_api_version: str
  auth_mode: str = "static_token"
  profile: dict[str, Any] | None = None
  ad_accounts: list[dict[str, Any]] = Field(default_factory=list)
  message: str | None = None


class MetaExportRequest(BaseModel):
  variant_ids: list[UUID]
  campaign_name: str
  ad_set_name: str | None = None


class MetaExportResponse(BaseModel):
  status: str
  auth_mode: str
  campaign_name: str
  ad_set_name: str | None = None
  variant_ids: list[str]
  ad_account_id: str | None = None
  message: str
