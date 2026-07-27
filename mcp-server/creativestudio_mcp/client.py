"""HTTP client for the CreativeStudio AI REST API."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx


class CreativeStudioError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class CreativeStudioClient:
    def __init__(
        self,
        api_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
        access_token: str | None = None,
        timeout: float = 120.0,
    ):
        self.api_url = (api_url or os.getenv("CREATIVESTUDIO_API_URL", "http://localhost:8000/api/v1")).rstrip(
            "/"
        )
        self.email = email or os.getenv("CREATIVESTUDIO_EMAIL", "")
        self.password = password or os.getenv("CREATIVESTUDIO_PASSWORD", "")
        self.access_token = access_token or os.getenv("CREATIVESTUDIO_ACCESS_TOKEN", "")
        self.refresh_token = ""
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def ensure_auth(self) -> None:
        if self.access_token:
            return
        if not self.email or not self.password:
            raise CreativeStudioError(
                "Set CREATIVESTUDIO_ACCESS_TOKEN or CREATIVESTUDIO_EMAIL + CREATIVESTUDIO_PASSWORD"
            )
        data = self.request(
            "POST",
            "/auth/login",
            json_body={"email": self.email, "password": self.password},
            auth=False,
        )
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", "")

    def _try_refresh(self) -> bool:
        if not self.refresh_token:
            # Re-login if we only have email/password
            if self.email and self.password:
                self.access_token = ""
                self.ensure_auth()
                return True
            return False
        try:
            data = self.request(
                "POST",
                "/auth/refresh",
                json_body={"refresh_token": self.refresh_token},
                auth=False,
            )
            self.access_token = data["access_token"]
            self.refresh_token = data.get("refresh_token", self.refresh_token)
            return True
        except CreativeStudioError:
            if self.email and self.password:
                self.access_token = ""
                self.refresh_token = ""
                self.ensure_auth()
                return True
            return False

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        auth: bool = True,
    ) -> Any:
        if auth:
            self.ensure_auth()

        url = f"{self.api_url}{path}"
        response = self._client.request(
            method,
            url,
            headers=self._headers(),
            params=params,
            json=json_body,
        )

        if response.status_code == 401 and auth:
            if self._try_refresh():
                response = self._client.request(
                    method,
                    url,
                    headers=self._headers(),
                    params=params,
                    json=json_body,
                )

        if response.status_code == 204:
            return {"ok": True}

        try:
            body: Any = response.json()
        except Exception:
            body = response.text

        if response.status_code >= 400:
            detail = body.get("detail") if isinstance(body, dict) else body
            raise CreativeStudioError(
                f"{method} {path} failed ({response.status_code}): {detail}",
                status_code=response.status_code,
                body=body,
            )
        return body

    def dump(self, data: Any) -> str:
        return json.dumps(data, indent=2, default=str)


_client: Optional[CreativeStudioClient] = None


def get_client() -> CreativeStudioClient:
    global _client
    if _client is None:
        _client = CreativeStudioClient()
    return _client
