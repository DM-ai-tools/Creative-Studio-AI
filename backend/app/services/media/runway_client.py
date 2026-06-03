"""Shared Runway ML API client (https://docs.dev.runwayml.com/)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5
POLL_MAX_ATTEMPTS = 120


def runway_configured() -> bool:
    return bool(settings.RUNWAYML_API_KEY.strip())


def runway_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.RUNWAYML_API_KEY}",
        "Content-Type": "application/json",
        "X-Runway-Version": settings.RUNWAYML_API_VERSION,
    }


def runway_base_url() -> str:
    return settings.RUNWAYML_BASE_URL.rstrip("/")


def ratio_for_video(format_type: str) -> str:
    if format_type in {"reel", "video"}:
        return settings.RUNWAYML_VIDEO_RATIO
    if format_type == "carousel":
        return "1920:1080"
    return settings.RUNWAYML_IMAGE_RATIO


def file_url_to_data_uri(file_url: str | None) -> str | None:
    if not file_url:
        return None
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    rel: Path | None = None
    if file_url.startswith("/files/"):
        rel = Path(file_url.removeprefix("/files/"))
    elif file_url.startswith("files/"):
        rel = Path(file_url.removeprefix("files/"))
    if rel is None:
        return file_url if file_url.startswith("http") or file_url.startswith("data:") else None
    path = (upload_root / rel).resolve()
    try:
        path.relative_to(upload_root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/png")
    content = path.read_bytes()
    import base64

    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def file_url_to_data_uri_for_video(file_url: str | None) -> str | None:
    """Like file_url_to_data_uri but pads image to satisfy Runway video API limits."""
    if not file_url:
        return None
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    rel: Path | None = None
    if file_url.startswith("/files/"):
        rel = Path(file_url.removeprefix("/files/"))
    elif file_url.startswith("files/"):
        rel = Path(file_url.removeprefix("files/"))
    if rel is None:
        return file_url_to_data_uri(file_url)
    path = (upload_root / rel).resolve()
    try:
        path.relative_to(upload_root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    from app.services.logo_overlay import pad_image_bytes_for_runway_video

    import base64

    content = pad_image_bytes_for_runway_video(path.read_bytes())
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:image/png;base64,{encoded}"


_TRANSIENT_MARKERS = (
    "high load",
    "try again later",
    "rate limit",
    "too many requests",
    "temporarily unavailable",
    "service unavailable",
)


def is_transient_runway_error(exc: Exception) -> bool:
    """True when Runway is overloaded or rate-limited — safe to resubmit after a delay."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        if exc.response.status_code in {429, 502, 503, 504}:
            return True
    raw = str(exc).lower()
    return any(marker in raw for marker in _TRANSIENT_MARKERS)


async def submit_task(client: httpx.AsyncClient, path: str, payload: dict[str, Any]) -> str:
    response = await client.post(f"{runway_base_url()}{path}", json=payload, headers=runway_headers())
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"Runway submit failed: {response.text[:500]}",
            request=response.request,
            response=response,
        )
    body = response.json()
    task_id = body.get("id")
    if not task_id:
        raise ValueError(f"Runway response missing task id: {body}")
    return str(task_id)


async def submit_task_and_wait(
    client: httpx.AsyncClient,
    path: str,
    payload: dict[str, Any],
    *,
    label: str = "Runway",
) -> list[str]:
    """Submit a Runway task, poll until done, and retry on transient overload failures."""
    attempts = max(1, settings.RUNWAYML_TRANSIENT_RETRY_ATTEMPTS)
    base_delay = max(1.0, settings.RUNWAYML_TRANSIENT_RETRY_BASE_SEC)
    last_exc: Exception | None = None

    for attempt in range(attempts):
        if attempt:
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "%s overloaded (attempt %s/%s) — retrying in %ss",
                label,
                attempt + 1,
                attempts,
                int(delay),
            )
            await asyncio.sleep(delay)
        try:
            task_id = await submit_task(client, path, payload)
            return await wait_for_task_output(client, task_id)
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1 and is_transient_runway_error(exc):
                continue
            raise

    if last_exc:
        raise last_exc
    raise RuntimeError(f"{label} task failed with no error detail")


async def wait_for_task_output(client: httpx.AsyncClient, task_id: str) -> list[str]:
    for attempt in range(POLL_MAX_ATTEMPTS):
        if attempt:
            await asyncio.sleep(POLL_INTERVAL_SEC)
        response = await client.get(
            f"{runway_base_url()}/tasks/{task_id}",
            headers=runway_headers(),
        )
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Runway poll failed: {response.text[:300]}",
                request=response.request,
                response=response,
            )
        body = response.json()
        status = (body.get("status") or "").upper()
        if status == "SUCCEEDED":
            output = body.get("output") or []
            if not output:
                raise ValueError("Runway task succeeded but returned no output URLs")
            return [str(url) for url in output]
        if status in {"FAILED", "CANCELED", "CANCELLED"}:
            failure = body.get("failure") or body.get("failureCode") or body
            raise RuntimeError(f"Runway task {status}: {failure}")
    raise TimeoutError(f"Runway task {task_id} timed out after polling")
