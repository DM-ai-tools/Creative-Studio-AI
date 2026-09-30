"""BytePlus ModelArk (Dreamina) Seedance video API — create task + poll."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.services.http_retry import async_request_with_retry, is_transient_http_error

logger = logging.getLogger(__name__)

DEFAULT_ARK_BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"
DEFAULT_SEEDANCE_MODEL = "dreamina-seedance-2-0-260128"
DEFAULT_SEEDANCE_25_MODEL = "dreamina-seedance-2-5-260628"
SEEDANCE_25_CATALOG_IDS = frozenset(
    {
        "ark-seedance-2-5",
        "byteplus-seedance-2-5",
        "seedance-2-5-byteplus",
        "dreamina-seedance-2-5",
    }
)
# BytePlus Seedance 2.5 accepts these explicit ratios (4:5 is not supported in r2v).
SEEDANCE_25_SUPPORTED_RATIOS = frozenset(
    {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"}
)
SEEDANCE_25_RATIO_FALLBACKS = {
    "4:5": "3:4",
    "5:4": "4:3",
}


def ark_configured() -> bool:
    return bool((settings.ARK_API_KEY or "").strip())


def ark_base_url() -> str:
    return (settings.ARK_BASE_URL or DEFAULT_ARK_BASE).rstrip("/")


def ark_seedance_model() -> str:
    return (settings.ARK_SEEDANCE_MODEL or DEFAULT_SEEDANCE_MODEL).strip()


def ark_seedance_25_model() -> str:
    return (settings.ARK_SEEDANCE_25_MODEL or DEFAULT_SEEDANCE_25_MODEL).strip()


def is_seedance_25_model(model: str | None) -> bool:
    mid = (model or "").strip().lower().replace("_", "-")
    if not mid:
        return False
    if mid in SEEDANCE_25_CATALOG_IDS:
        return True
    if "dreamina-seedance-2-5" in mid or "seedance-2-5" in mid:
        return True
    return "2-5" in mid or "2.5" in mid


def seedance_clip_cap_seconds(model: str | None) -> int:
    return 30 if is_seedance_25_model(model) else 15


def resolve_seedance_api_model(model: str | None) -> str:
    mid = (model or "").strip()
    if mid.startswith("dreamina-seedance"):
        return mid
    if is_seedance_25_model(mid):
        return ark_seedance_25_model()
    return ark_seedance_model()


def ark_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.ARK_API_KEY.strip()}",
        "Content-Type": "application/json",
    }


def seedance_async_client() -> httpx.AsyncClient:
    """
    Seedance jobs poll for several minutes. Disable keep-alive so each request
    uses a fresh TCP connection (avoids stale-socket ConnectError mid-poll).
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=45.0, read=120.0, write=120.0, pool=30.0),
        limits=httpx.Limits(max_keepalive_connections=0, max_connections=20),
        follow_redirects=True,
    )


def is_seedance_transport_error(exc: BaseException | str) -> bool:
    """True for network/connect failures talking to BytePlus ModelArk."""
    if is_transient_http_error(exc if isinstance(exc, BaseException) else RuntimeError(str(exc))):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "all connection attempts failed",
            "connecterror",
            "connection refused",
            "connection reset",
            "temporary failure in name resolution",
            "timed out while connecting",
        )
    )


def map_aspect_to_ratio(aspect: str | None, format_type: str | None = None) -> str:
    raw = (aspect or "").replace(":", "/").strip()
    mapping = {
        "9/16": "9:16",
        "1/4": "9:16",
        "16/9": "16:9",
        "1/1": "1:1",
        "4/3": "4:3",
        "4/5": "4:5",
        "5/4": "5:4",
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


def seedance_reference_data_uri(file_url: str | None) -> str | None:
    """Load a reference image and pad it to BytePlus Seedance upload limits."""
    import base64

    from app.services.logo_overlay import (
        file_url_to_local_path,
        pad_image_bytes_for_seedance_reference,
    )

    if not file_url:
        return None
    url = str(file_url).strip()
    if not url:
        return None

    def _encode(image_bytes: bytes) -> str:
        padded = pad_image_bytes_for_seedance_reference(image_bytes)
        encoded = base64.b64encode(padded).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    if url.startswith("data:"):
        try:
            header, payload = url.split(",", 1)
            mime = header.split(";")[0].removeprefix("data:")
            if mime not in {"image/png", "image/jpeg", "image/webp"}:
                mime = "image/png"
            import base64 as b64

            return _encode(b64.b64decode(payload))
        except Exception:
            return url

    path = file_url_to_local_path(url)
    if path and path.is_file():
        return _encode(path.read_bytes())

    if url.startswith("http://") or url.startswith("https://"):
        try:
            response = httpx.get(url, timeout=45.0, follow_redirects=True)
            response.raise_for_status()
            return _encode(response.content)
        except Exception as exc:
            logger.warning("Could not pad remote Seedance reference %s: %s", url[:80], exc)
            return url

    from app.services.media.runway_client import file_url_to_data_uri

    return file_url_to_data_uri(url)


def resolve_seedance_api_ratio(
    aspect: str | None,
    format_type: str | None = None,
    *,
    model: str | None = None,
    frame_locked: bool = False,
) -> tuple[str, str | None]:
    """Map UI aspect to a BytePlus Seedance ratio, with 2.5-specific fallbacks."""
    requested = map_aspect_to_ratio(aspect, format_type)
    if not is_seedance_25_model(model):
        return requested, None
    if frame_locked:
        if requested != "adaptive":
            return (
                "adaptive",
                (
                    f"Seedance 2.5 first-frame generation requires adaptive ratio "
                    f"(requested {requested})."
                ),
            )
        return "adaptive", None
    if requested in SEEDANCE_25_SUPPORTED_RATIOS:
        return requested, None
    fallback = SEEDANCE_25_RATIO_FALLBACKS.get(requested, "9:16")
    return (
        fallback,
        (
            f"Seedance 2.5 does not support {requested} (Meta feed 4:5 is not on BytePlus); "
            f"using {fallback} instead — crop to {requested} in post if needed."
        ),
    )


def clamp_seedance_duration(seconds: int | None, *, max_seconds: int = 15) -> int:
    try:
        n = int(seconds or 5)
    except (TypeError, ValueError):
        n = 5
    return max(4, min(max_seconds, n))


def map_resolution(resolution: str | None, *, model: str | None = None) -> str:
    r = (resolution or "720p").strip().lower()
    if is_seedance_25_model(model):
        if r in {"480p", "720p", "1080p"}:
            return r
        return "1080p"
    if r in {"480p", "720p", "1080p"}:
        return r
    if r in {"4k", "2160p", "2k", "1440p"}:
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
    from app.services.creative_studio_timeline import validate_video_prompt

    content: list[dict[str, Any]] = [
        {"type": "text", "text": validate_video_prompt(prompt)},
    ]
    if image_data_uri_or_url:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": image_data_uri_or_url},
                "role": image_role,
            }
        )
    # BytePlus rejects a task that mixes first/last-frame conditioning with
    # reference media. Enforce the provider contract at the HTTP boundary as a
    # final safeguard even if an upstream caller accidentally supplies both.
    frame_locked = bool(image_data_uri_or_url) and image_role in {"first_frame", "last_frame"}
    safe_extra_refs = [] if frame_locked else (extra_image_refs or [])
    for ref in safe_extra_refs[:9 - int(bool(image_data_uri_or_url))]:
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

    api_model = (model or ark_seedance_model()).strip()
    task_ratio = ratio
    if (
        image_data_uri_or_url
        and image_role in {"first_frame", "last_frame"}
        and is_seedance_25_model(api_model)
        and task_ratio != "adaptive"
    ):
        task_ratio = "adaptive"
    payload: dict[str, Any] = {
        "model": api_model,
        "content": content,
        "duration": clamp_seedance_duration(
            duration,
            max_seconds=seedance_clip_cap_seconds(api_model),
        ),
        "ratio": task_ratio,
        "resolution": map_resolution(resolution, model=api_model),
        "generate_audio": bool(generate_audio),
        "watermark": False,
    }
    url = f"{ark_base_url()}/contents/generations/tasks"
    response = await async_request_with_retry(
        client,
        "POST",
        url,
        json=payload,
        headers=ark_headers(),
        timeout=120.0,
        label="BytePlus Seedance create",
        max_attempts=6,
    )
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
        response = await async_request_with_retry(
            client,
            "GET",
            url,
            headers=ark_headers(),
            timeout=60.0,
            label=f"{label} poll",
            max_attempts=5,
        )
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
