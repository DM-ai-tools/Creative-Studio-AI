"""BytePlus ModelArk (Dreamina) Seedance video API — create task + poll."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_ARK_BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"
DEFAULT_SEEDANCE_MODEL = "dreamina-seedance-2-0-260128"


def ark_configured() -> bool:
    return bool((settings.ARK_API_KEY or "").strip())


def ark_base_url() -> str:
    return (settings.ARK_BASE_URL or DEFAULT_ARK_BASE).rstrip("/")


def ark_seedance_model() -> str:
    return (settings.ARK_SEEDANCE_MODEL or DEFAULT_SEEDANCE_MODEL).strip()


def ark_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.ARK_API_KEY.strip()}",
        "Content-Type": "application/json",
    }


def map_aspect_to_ratio(aspect: str | None, format_type: str | None = None) -> str:
    raw = (aspect or "").replace(":", "/").strip()
    mapping = {
        "9/16": "9:16",
        "1/4": "9:16",
        "16/9": "16:9",
        "1/1": "1:1",
        "4/3": "4:3",
        "3/4": "3:4",
    }
    if raw in mapping:
        return mapping[raw]
    ft = (format_type or "").lower()
    if ft in {"reel", "stories", "video"}:
        return "9:16"
    if ft == "carousel":
        return "4:3"
    return "9:16"


def clamp_seedance_duration(seconds: int | None, *, max_seconds: int = 15) -> int:
    try:
        n = int(seconds or 5)
    except (TypeError, ValueError):
        n = 5
    return max(4, min(max_seconds, n))


def map_resolution(resolution: str | None) -> str:
    r = (resolution or "720p").strip().lower()
    if r in {"480p", "720p", "1080p"}:
        return r
    if r in {"4k", "2160p"}:
        return "1080p"
    return "720p"


async def create_video_task(
    client: httpx.AsyncClient,
    *,
    prompt: str,
    model: str | None = None,
    duration: int = 5,
    ratio: str = "9:16",
    resolution: str = "720p",
    generate_audio: bool = False,
    image_data_uri_or_url: str | None = None,
    image_role: str = "first_frame",
    extra_image_refs: list[dict[str, str]] | None = None,
) -> str:
    """
    Create a Seedance task.

    Seedance 2.0 accepts multiple reference images (up to ~9) in one unified pass —
    pass storyboard frames via extra_image_refs: [{url, role}].
    """
    content: list[dict[str, Any]] = [
        {"type": "text", "text": (prompt or "").strip()[:4000] or "Product ad scene"},
    ]
    if image_data_uri_or_url:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": image_data_uri_or_url},
                "role": image_role,
            }
        )
    for ref in (extra_image_refs or [])[:8]:
        url = str(ref.get("url") or "").strip()
        if not url:
            continue
        role = str(ref.get("role") or "reference_image").strip() or "reference_image"
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": url},
                "role": role,
            }
        )

    payload: dict[str, Any] = {
        "model": (model or ark_seedance_model()).strip(),
        "content": content,
        "duration": clamp_seedance_duration(duration),
        "ratio": ratio,
        "resolution": map_resolution(resolution),
        "generate_audio": bool(generate_audio),
        "watermark": False,
    }
    url = f"{ark_base_url()}/contents/generations/tasks"
    response = await client.post(url, json=payload, headers=ark_headers(), timeout=120.0)
    if response.status_code >= 400:
        body = (response.text or "")[:800]
        raise RuntimeError(f"BytePlus Seedance create failed ({response.status_code}): {body}")
    data = response.json() if response.content else {}
    task_id = str(data.get("id") or data.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError(f"BytePlus Seedance create returned no task id: {data!r}"[:400])
    return task_id


def is_seedance_person_privacy_block(exc: BaseException | str) -> bool:
    """True when BytePlus rejects a seed still as looking like a real person (privacy filter)."""
    text = str(exc)
    markers = (
        "InputImageSensitiveContentDetected.PrivacyInformation",
        "may contain real person",
        "PrivacyInformation",
    )
    return any(m in text for m in markers)


async def poll_video_task(
    client: httpx.AsyncClient,
    task_id: str,
    *,
    label: str = "BytePlus Seedance",
    cancel_check: Any | None = None,
) -> dict[str, Any]:
    max_wait = max(60, int(settings.ARK_POLL_MAX_WAIT_SECONDS or 1800))
    interval = 4.0
    elapsed = 0.0
    url = f"{ark_base_url()}/contents/generations/tasks/{task_id}"
    last: dict[str, Any] = {}

    while elapsed < max_wait:
        if cancel_check and cancel_check():
            try:
                await delete_video_task(task_id, client=client)
            except Exception as exc:
                logger.warning("Delete Seedance task on cancel failed: %s", exc)
            raise RuntimeError(f"{label} cancelled by user")
        response = await client.get(url, headers=ark_headers(), timeout=60.0)
        if response.status_code >= 400:
            body = (response.text or "")[:500]
            raise RuntimeError(f"{label} poll failed ({response.status_code}): {body}")
        last = response.json() if response.content else {}
        status = str(last.get("status") or "").lower()
        if status in {"succeeded", "success", "completed", "done"}:
            return last
        if status in {"failed", "error", "cancelled", "canceled"}:
            err = (
                last.get("error")
                or last.get("message")
                or last.get("fail_reason")
                or last
            )
            raise RuntimeError(f"{label} task failed: {err}"[:500])
        await asyncio.sleep(interval)
        elapsed += interval
        if interval < 12:
            interval = min(12.0, interval + 1.0)

    raise TimeoutError(f"{label} timed out after {max_wait}s (task {task_id})")


async def delete_video_task(
    task_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Cancel/delete a Seedance task (BytePlus DELETE /contents/generations/tasks/{id})."""
    tid = (task_id or "").strip()
    if not tid or not ark_configured():
        return
    url = f"{ark_base_url()}/contents/generations/tasks/{tid}"
    owns = client is None
    http = client or httpx.AsyncClient(timeout=60.0)
    try:
        response = await http.delete(url, headers=ark_headers())
        if response.status_code >= 400 and response.status_code != 404:
            logger.warning(
                "BytePlus delete task %s → %s %s",
                tid,
                response.status_code,
                (response.text or "")[:200],
            )
    finally:
        if owns:
            await http.aclose()


def extract_video_url(task: dict[str, Any]) -> str | None:
    content = task.get("content")
    if isinstance(content, dict):
        url = content.get("video_url") or content.get("url")
        if url:
            return str(url)
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            url = item.get("video_url") or item.get("url")
            if isinstance(url, dict):
                url = url.get("url")
            if url:
                return str(url)
    for key in ("video_url", "output_url", "url"):
        if task.get(key):
            return str(task[key])
    return None
