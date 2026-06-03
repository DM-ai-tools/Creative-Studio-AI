"""Resilient HTTP helpers for long-running provider calls (HeyGen, Runway, CDN downloads)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TRANSIENT_STATUS = frozenset({429, 502, 503, 504})


def is_transient_http_error(exc: BaseException) -> bool:
    """True for timeouts, connection resets, and overloaded upstream responses."""
    if isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        ),
    ):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return exc.response.status_code in _TRANSIENT_STATUS
    msg = str(exc).lower()
    if "connection attempts failed" in msg or "connection reset" in msg:
        return True
    return False


def humanize_http_error(exc: BaseException | str) -> str:
    """Map low-level httpx/httpcore errors to actionable messages."""
    text = str(exc).strip()
    lower = text.lower()
    if "connection attempts failed" in lower or isinstance(exc, httpx.ConnectError):
        return (
            "Could not reach HeyGen (network connection failed). "
            "Check your internet, VPN, and firewall, ensure https://api.heygen.com is reachable, "
            "then click Generate again — the server will retry automatically."
        )
    if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return (
            "HeyGen request timed out. The video may still be processing — wait a minute and regenerate, "
            "or check HeyGen dashboard for the render status."
        )
    if "insufficient" in lower and "credit" in lower:
        return (
            "HeyGen API credits are empty. Add credits in HeyGen → Settings → API, then regenerate."
        )
    if isinstance(exc, TimeoutError) or "heygen video timed out" in lower:
        return (
            "HeyGen is still rendering your video (waited up to 60 minutes). "
            "Video Agent often takes 15–35 minutes for a 30-second ad. "
            "Wait a few minutes, then click Generate again — do not spam regenerate."
        )
    return text


async def async_request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_attempts: int = 8,
    base_delay_sec: float = 2.0,
    max_delay_sec: float = 45.0,
    label: str = "HTTP",
    **kwargs: Any,
) -> httpx.Response:
    """Retry GET/POST on transient network failures with exponential backoff."""
    attempts = max(1, int(max_attempts))
    last_exc: BaseException | None = None
    method_upper = method.upper()

    for attempt in range(attempts):
        if attempt:
            delay = min(max_delay_sec, base_delay_sec * (2 ** (attempt - 1)))
            logger.warning(
                "%s %s transient failure (attempt %s/%s) — retry in %.1fs: %s",
                label,
                method_upper,
                attempt + 1,
                attempts,
                delay,
                last_exc,
            )
            await asyncio.sleep(delay)
        try:
            response = await client.request(method_upper, url, **kwargs)
            if response.status_code in _TRANSIENT_STATUS and attempt < attempts - 1:
                last_exc = httpx.HTTPStatusError(
                    f"{label} returned {response.status_code}",
                    request=response.request,
                    response=response,
                )
                continue
            return response
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1 and is_transient_http_error(exc):
                continue
            raise

    if last_exc:
        raise last_exc
    raise RuntimeError(f"{label} {method_upper} failed with no error detail")


def heygen_async_client() -> httpx.AsyncClient:
    """
    HeyGen jobs poll for 10–15 minutes. Disable keep-alive so each poll uses a
    fresh TCP connection (avoids 'All connection attempts failed' on stale sockets).
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=30.0, read=90.0, write=60.0, pool=30.0),
        limits=httpx.Limits(max_keepalive_connections=0, max_connections=20),
        follow_redirects=True,
    )
