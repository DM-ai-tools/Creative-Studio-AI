"""Gemini Omni 1.1 Flash video generation through the Gemini Interactions REST API."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.core.config import settings
from app.services.file_service import file_service
from app.services.media.base import VideoGenerationProvider
from app.services.media.gemini_omni_catalog import GEMINI_OMNI_MODEL_ID
from app.services.media.openai_image_provider import _load_reference_image_bytes
from app.services.usage_tracker import record_usage

logger = logging.getLogger(__name__)

_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_ALLOWED_RESOLUTIONS = {"360p", "720p", "1080p", "4k"}


def is_gemini_omni_model(model: str | None) -> bool:
    value = str(model or "").strip().lower()
    return value in {
        GEMINI_OMNI_MODEL_ID,
        "gemini-omni-1-1-flash",
        "gemini-omni-1.1-flash-preview",
    }


def _gemini_api_key() -> str:
    key = str(getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if key:
        return key
    # Uvicorn loads .env only at process start; re-read when the key was added
    # to backend/.env without restarting (common in local dev).
    try:
        from app.core.config import Settings

        key = str(Settings().GEMINI_API_KEY or "").strip()
    except Exception:
        key = ""
    return key


def gemini_omni_configured() -> bool:
    return bool(_gemini_api_key())


def clamp_gemini_omni_duration(seconds: int | float | None) -> int:
    return max(3, min(10, int(round(float(seconds or 10)))))


def _aspect_for(format_type: str, requested: str) -> tuple[str, str | None]:
    raw = str(requested or "").replace("/", ":").strip()
    if raw in {"9:16", "16:9"}:
        return raw, None
    if str(format_type or "").lower() in {"reel", "stories"}:
        return "9:16", f"Gemini Omni does not support {raw or 'this aspect'}; generated at 9:16."
    return "16:9", f"Gemini Omni does not support {raw or 'this aspect'}; generated at 16:9."


def _resolution_for(requested: str) -> tuple[str, str | None]:
    raw = str(requested or "720p").strip().lower()
    if raw in _ALLOWED_RESOLUTIONS:
        return raw, None
    if raw == "480p":
        return "360p", "Gemini Omni does not support 480p; generated at 360p."
    return "720p", f"Gemini Omni does not support {raw}; generated at 720p."


def _append_api_key(url: str, api_key: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["key"] = api_key
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _video_content(response: dict[str, Any]) -> dict[str, Any] | None:
    for step in response.get("steps") or []:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for item in step.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "video":
                return item
    output = response.get("output_video")
    return output if isinstance(output, dict) else None


def _usage_cost(usage: dict[str, Any], duration: int) -> tuple[int, int, int, float, bool]:
    input_tokens = int(usage.get("total_input_tokens") or 0)
    output_tokens = int(usage.get("total_output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    video_tokens = 0
    for item in usage.get("output_tokens_by_modality") or []:
        if isinstance(item, dict) and str(item.get("modality") or "").lower() == "video":
            video_tokens += int(item.get("tokens") or 0)
    if total_tokens or input_tokens or output_tokens:
        text_output = max(0, output_tokens - video_tokens)
        cost = (
            input_tokens * 1.50 / 1_000_000
            + video_tokens * 17.50 / 1_000_000
            + text_output * 9.00 / 1_000_000
        )
        return input_tokens, output_tokens, total_tokens, round(cost, 6), False
    return 0, 0, 0, round(float(duration) * 0.10, 6), True


def _reference_input(prompt: str, source_image_url: str | None, brief: dict) -> Any:
    presenter = str(
        brief.get("presenter_reference_url")
        or source_image_url
        or ""
    ).strip()
    asset_urls: list[str] = []
    character_urls: list[str] = []
    other_urls: list[str] = []
    for item in brief.get("reference_assets") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "reference").strip().lower()
        url = str(item.get("url") or "").strip()
        if not url or role == "proof":
            continue
        if role == "character":
            character_urls.append(url)
        else:
            other_urls.append(url)
    urls: list[str] = []
    for raw in [
        presenter,
        source_image_url,
        *character_urls,
        brief.get("product_reference_url"),
        *other_urls,
    ]:
        value = str(raw or "").strip()
        if value and value not in urls:
            urls.append(value)
    content: list[dict[str, str]] = []
    for url in urls[:4]:
        loaded = _load_reference_image_bytes(url)
        if not loaded:
            continue
        raw, _name, mime = loaded
        content.append({
            "type": "image",
            "data": base64.b64encode(raw).decode("ascii"),
            "mime_type": mime,
        })
    if not content:
        return prompt
    content.append({"type": "text", "text": prompt})
    return content


def _interaction_request_body(
    *,
    prompt: str,
    brief: dict,
    source_image_url: str | None,
    aspect: str,
    resolution: str,
    duration: int,
) -> dict[str, Any]:
    """Build one Omni request without mixing incompatible continuation modes.

    A stored multi-turn continuation uses ``previous_interaction_id`` and a new
    user input. Google rejects combining that stateful path with an explicit
    ``video_config.task=extend`` payload ("Only user input is allowed...").
    Prompting the continuation is the documented primary path, so the task is
    intentionally inferred by the model here.
    """
    previous_id = str(brief.get("gemini_previous_interaction_id") or "").strip()
    body: dict[str, Any] = {
        "model": GEMINI_OMNI_MODEL_ID,
        "input": _reference_input(prompt, source_image_url, brief),
        "store": True,
        "response_format": {
            "type": "video",
            "aspect_ratio": aspect,
            "resolution": resolution,
            "duration": f"{duration}s",
            **({"delivery": "uri"} if resolution in {"1080p", "4k"} else {}),
        },
    }
    if previous_id:
        body["previous_interaction_id"] = previous_id
    return body


async def _download_uri_video(client: httpx.AsyncClient, uri: str, api_key: str) -> bytes:
    file_match = re.search(r"/files/([^/:?]+)", uri)
    if file_match:
        file_id = file_match.group(1)
        status_url = _append_api_key(
            f"https://generativelanguage.googleapis.com/v1beta/files/{file_id}",
            api_key,
        )
        for _ in range(180):
            status = await client.get(status_url)
            status.raise_for_status()
            payload = status.json()
            state = str(payload.get("state") or "").upper()
            if state == "FAILED":
                raise RuntimeError("Gemini Omni video file processing failed")
            if state in {"ACTIVE", "SUCCEEDED", "COMPLETED"}:
                break
            await asyncio.sleep(5)
        else:
            raise TimeoutError("Gemini Omni video file did not become active within 15 minutes")
    response = await client.get(_append_api_key(uri, api_key))
    response.raise_for_status()
    return response.content


class GeminiOmniVideoProvider(VideoGenerationProvider):
    provider_id = "google"

    async def generate(
        self,
        *,
        prompt: str,
        brief: dict,
        copy: dict,
        format_type: str,
        model: str,
        tenant_id: str,
        source_image_url: str | None = None,
        duration_seconds: int | None = None,
    ) -> dict:
        api_key = _gemini_api_key()
        duration = clamp_gemini_omni_duration(duration_seconds)
        if not api_key:
            return {
                "status": "failed",
                "provider": "google",
                "model": GEMINI_OMNI_MODEL_ID,
                "error": "GEMINI_API_KEY is not configured",
                "retryable": False,
            }
        aspect, aspect_warning = _aspect_for(
            format_type,
            str(brief.get("creative_studio_aspect") or brief.get("aspect") or "16:9"),
        )
        resolution, resolution_warning = _resolution_for(
            str(brief.get("creative_studio_resolution") or brief.get("resolution") or "720p")
        )
        previous_id = str(brief.get("gemini_previous_interaction_id") or "").strip()
        body = _interaction_request_body(
            prompt=prompt,
            brief=brief,
            source_image_url=source_image_url,
            aspect=aspect,
            resolution=resolution,
            duration=duration,
        )

        error_text = ""
        try:
            timeout = httpx.Timeout(1000.0, connect=30.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.post(
                    _INTERACTIONS_URL,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=body,
                )
                if response.status_code >= 400:
                    error_text = response.text[:1500]
                    response.raise_for_status()
                payload = response.json()
                if isinstance(payload.get("interaction"), dict):
                    payload = payload["interaction"]
                video = _video_content(payload)
                if not video:
                    raise RuntimeError("Gemini Omni response contained no video output")
                if video.get("data"):
                    video_bytes = base64.b64decode(str(video["data"]))
                elif video.get("uri"):
                    video_bytes = await _download_uri_video(client, str(video["uri"]), api_key)
                else:
                    raise RuntimeError("Gemini Omni video output had no data or URI")
            saved = file_service.save_bytes(
                content=video_bytes,
                tenant_id=tenant_id,
                subfolder="generated",
                suffix=".mp4",
                content_type="video/mp4",
            )
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            prompt_tokens, completion_tokens, total_tokens, cost, estimated = _usage_cost(
                usage, duration
            )
            record_usage(
                provider="google",
                model=GEMINI_OMNI_MODEL_ID,
                operation="video_generation",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost,
                success=True,
                tenant_id=tenant_id,
                extra={
                    "video_url": saved["file_url"],
                    "duration_seconds": duration,
                    "media_type": "video",
                    "interaction_id": str(payload.get("id") or ""),
                    "previous_interaction_id": previous_id,
                    "cost_estimated": estimated,
                    "resolution": resolution,
                    "aspect": aspect,
                },
            )
            warnings = " ".join(v for v in (aspect_warning, resolution_warning) if v)
            return {
                "status": "done",
                "provider": "google",
                "model": GEMINI_OMNI_MODEL_ID,
                "url": saved["file_url"],
                "duration_seconds": duration,
                "interaction_id": str(payload.get("id") or ""),
                "previous_interaction_id": previous_id or None,
                "provider_usage": [{
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cost_usd": cost,
                    "cost_estimated": estimated,
                }],
                "duration_warning": warnings or None,
                "voiceover": {"status": "native", "provider": "gemini-omni"},
            }
        except Exception as exc:
            message = error_text or str(exc) or type(exc).__name__
            record_usage(
                provider="google",
                model=GEMINI_OMNI_MODEL_ID,
                operation="video_generation",
                success=False,
                error=message[:2000],
                tenant_id=tenant_id,
                extra={
                    "duration_seconds": duration,
                    "media_type": "video",
                    "previous_interaction_id": previous_id,
                },
            )
            logger.exception("Gemini Omni video generation failed")
            return {
                "status": "failed",
                "provider": "google",
                "model": GEMINI_OMNI_MODEL_ID,
                "error": message[:1500],
                "retryable": False,
            }
