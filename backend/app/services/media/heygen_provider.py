"""HeyGen video — v3 Video Agent (primary) or v2 avatar (optional fallback)."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.core.config import settings
from app.services.http_retry import (
    async_request_with_retry,
    heygen_async_client,
    humanize_http_error,
)
from app.services.heygen_catalog import resolve_heygen_avatar_and_voice
from app.services.heygen_prompt import HEYGEN_V3_PROMPT_MAX, clamp_heygen_v3_prompt
from app.services.media.base import VideoGenerationProvider
from app.services.media.runway_providers import _download_asset
from app.services.video_duration import requested_video_duration_seconds
from app.services.video_script_skeleton import (
    build_heygen_agent_prompt,
    ensure_production_skeleton,
    resolve_heygen_spoken_script,
    resolve_stats_image_urls,
)

logger = logging.getLogger(__name__)

HEYGEN_MODEL_ID = "heygen-video-agent"
HEYGEN_V2_MODEL_ID = "heygen-avatar-v2"


def is_heygen_video_model(model: str | None) -> bool:
    key = (model or "").strip().lower()
    return key == "heygen" or key.startswith("heygen-") or key.startswith("heygen_")

_V3_DONE_STATUSES = frozenset({"completed", "complete", "success", "done"})
_V3_FAIL_STATUSES = frozenset({"failed", "error"})


def _poll_meta_from_data(data: dict) -> dict:
    """Caption sidecar from HeyGen when available (best sync with avatar audio)."""
    caption = data.get("caption")
    cap_url = caption.get("url") if isinstance(caption, dict) else None
    subtitle_url = (
        data.get("subtitle_url")
        or data.get("caption_url")
        or data.get("srt_url")
        or cap_url
    )
    return {"subtitle_url": subtitle_url} if subtitle_url else {}


def heygen_configured() -> bool:
    return bool((settings.HEYGEN_API_KEY or "").strip())


def _heygen_settings(brief: dict) -> dict:
    raw = brief.get("heygen_settings")
    if isinstance(raw, dict):
        return raw
    kb = brief.get("key_benefits")
    if isinstance(kb, dict) and isinstance(kb.get("heygen_settings"), dict):
        return kb["heygen_settings"]
    return {}


def heygen_captions_enabled(brief: dict) -> bool:
    heygen = _heygen_settings(brief)
    if heygen.get("captions") is False or heygen.get("burn_in_captions") is False:
        return False
    return True


def _heygen_caption_api_payload(brief: dict) -> dict | None:
    """HeyGen v2/v3 Create Video API — burns captions into render when style is set."""
    if not heygen_captions_enabled(brief):
        return None
    return {"file_format": "srt", "style": "default"}


def _use_v3_primary() -> bool:
    return (settings.HEYGEN_VIDEO_API or "v3").strip().lower() != "v2"


def _heygen_v3_orientation(format_type: str, brief: dict | None = None) -> str:
    """HeyGen Video Agent orientation — creative format overrides conflicting card settings."""
    ft = (format_type or "").lower()
    if ft in {"reel", "stories"}:
        return "portrait"
    if ft == "video":
        return "landscape"
    brief = brief or {}
    heygen: dict = {}
    raw = brief.get("heygen_settings")
    if isinstance(raw, dict):
        heygen = raw
    else:
        kb = brief.get("key_benefits")
        if isinstance(kb, dict) and isinstance(kb.get("heygen_settings"), dict):
            heygen = kb["heygen_settings"]
    ar = str(
        heygen.get("aspect_ratio") or heygen.get("aspect_ratio_label") or ""
    ).lower()
    if "16:9" in ar or "16x9" in ar or "landscape" in ar:
        return "landscape"
    if "9:16" in ar or "9x16" in ar or "portrait" in ar or "vertical" in ar:
        return "portrait"
    return "landscape"


def _video_dimensions(format_type: str, brief: dict | None = None) -> dict[str, int]:
    """Output dimensions — creative format overrides HeyGen card aspect."""
    ft = (format_type or "").lower()
    if ft in {"reel", "stories"}:
        return {"width": 1080, "height": 1920}
    if ft == "video":
        return {"width": 1920, "height": 1080}
    heygen = None
    if brief:
        heygen = brief.get("heygen_settings")
        if not isinstance(heygen, dict):
            kb = brief.get("key_benefits")
            if isinstance(kb, dict):
                heygen = kb.get("heygen_settings")
    if isinstance(heygen, dict):
        ar = (
            str(
                heygen.get("aspect_ratio")
                or heygen.get("aspect_ratio_label")
                or heygen.get("aspect_ratio_custom")
                or ""
            )
            .lower()
        )
        if "16:9" in ar or "16x9" in ar:
            return {"width": 1920, "height": 1080}
        if "1:1" in ar or "square" in ar:
            return {"width": 1080, "height": 1080}
    return {"width": 1080, "height": 1080}


class HeyGenVideoProvider(VideoGenerationProvider):
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
        if not heygen_configured():
            return _fail("HEYGEN_API_KEY is not configured")

        from app.services.video_duration import MAX_VIDEO_DURATION_SECONDS

        target_duration = requested_video_duration_seconds(brief, override=duration_seconds)
        target_duration = max(5, min(MAX_VIDEO_DURATION_SECONDS, int(target_duration)))

        avatar_raw = brief.get("heygen_avatar_id") or settings.HEYGEN_AVATAR_ID
        prefer_portrait = format_type in {"reel", "stories"}
        try:
            avatar_id, default_voice = await asyncio.to_thread(
                resolve_heygen_avatar_and_voice,
                str(avatar_raw),
                prefer_portrait=prefer_portrait,
            )
        except ValueError as exc:
            return _fail(str(exc))

        voice_id = (brief.get("heygen_voice_id") or settings.HEYGEN_VOICE_ID or "").strip()
        if not voice_id and default_voice:
            voice_id = str(default_voice)
        if not voice_id:
            return _fail("HeyGen voice is not configured")

        production_skeleton = await ensure_production_skeleton(
            brief,
            copy,
            duration=target_duration,
            format_type=format_type,
        )
        from app.services.stats_image_service import ensure_avatar_script_cites_ocr_stats

        brief = ensure_avatar_script_cites_ocr_stats(
            {**brief, "video_script_skeleton": production_skeleton},
            duration=target_duration,
        )
        production_skeleton = str(brief.get("video_script_skeleton") or production_skeleton)
        script = resolve_heygen_spoken_script(
            brief,
            copy,
            production_skeleton=production_skeleton,
            target_seconds=target_duration,
        )
        from app.services.video_script_skeleton import (
            align_skeleton_to_spoken_script,
            merge_voice_and_broll_timeline,
            script_has_timed_lines,
            _heygen_scene_broll_raw,
        )

        kb = brief.get("key_benefits") if isinstance(brief.get("key_benefits"), dict) else {}
        timed_voice = str(brief.get("avatar_script") or kb.get("avatar_script") or "").strip()
        broll_raw = _heygen_scene_broll_raw(brief)
        if timed_voice and script_has_timed_lines(timed_voice):
            align_script = (
                merge_voice_and_broll_timeline(timed_voice, broll_raw)
                if broll_raw
                else timed_voice
            )
        else:
            align_script = script

        logger.info(
            "HEYGEN spoken script → %d words | approved_avatar=%s | preview: %s",
            len(script.split()),
            bool(timed_voice),
            script[:180].replace("\n", " "),
        )

        production_skeleton = align_skeleton_to_spoken_script(
            production_skeleton,
            align_script,
            duration=target_duration,
            brief=brief,
        )
        brief = {**brief, "video_script_skeleton": production_skeleton}
        base = settings.HEYGEN_BASE_URL.rstrip("/")
        headers = {"X-Api-Key": settings.HEYGEN_API_KEY, "Content-Type": "application/json"}

        model_key = (model or HEYGEN_MODEL_ID).strip().lower()
        force_v2 = model_key in (HEYGEN_V2_MODEL_ID, "heygen-v2", "heygen_avatar_v2")

        try:
            async with heygen_async_client() as client:
                if force_v2:
                    video_url, actual_duration, video_id, mode, poll_meta = (
                        await self._generate_v2_avatar(
                            client,
                            base,
                            headers,
                            brief=brief,
                            copy=copy,
                            avatar_id=avatar_id,
                            voice_id=voice_id,
                            script=script,
                            production_skeleton=production_skeleton,
                            format_type=format_type,
                            target_duration=target_duration,
                        )
                    )
                elif _use_v3_primary():
                    video_url, actual_duration, video_id, mode, poll_meta = await self._generate_with_v3_primary(
                        client,
                        base,
                        headers,
                        brief=brief,
                        copy=copy,
                        avatar_id=avatar_id,
                        voice_id=voice_id,
                        script=script,
                        production_skeleton=production_skeleton,
                        format_type=format_type,
                        target_duration=target_duration,
                    )
                else:
                    video_url, actual_duration, video_id, mode, poll_meta = await self._generate_v2_avatar(
                        client,
                        base,
                        headers,
                        brief=brief,
                        copy=copy,
                        avatar_id=avatar_id,
                        voice_id=voice_id,
                        script=script,
                        production_skeleton=production_skeleton,
                        format_type=format_type,
                        target_duration=target_duration,
                    )

                saved = await _download_asset(
                    client,
                    video_url,
                    tenant_id=tenant_id,
                    kind="video",
                )
                final_url = saved["url"]
                actual_duration: float = float(target_duration)
                trimmed = False
                from app.services.video_trim import trim_video_to_max_seconds

                trim_url, trim_dur = await asyncio.to_thread(
                    trim_video_to_max_seconds,
                    final_url,
                    tenant_id=tenant_id,
                    max_seconds=float(target_duration),
                )
                if trim_url:
                    final_url = trim_url
                    saved["url"] = trim_url
                    actual_duration = trim_dur or float(target_duration)
                    trimmed = True
                # Frame normalize runs once after finalize in ai_service (not here)
                fitted: str | None = None
                kb = brief.get("key_benefits") if isinstance(brief.get("key_benefits"), dict) else {}
                return {
                    "status": "done",
                    "model": HEYGEN_MODEL_ID,
                    "provider": "heygen",
                    "avatar_script": script,
                    "avatar_script_source": (
                        "pdf"
                        if (kb.get("script_source") == "pdf" or brief.get("script_source") == "pdf")
                        else "approved"
                    ),
                    "mode": mode,
                    "prompt": script,
                    "production_skeleton": production_skeleton,
                    "portrait_normalized": bool(fitted),
                    "frame_normalized": bool(fitted),
                    "trimmed_to_requested_duration": trimmed,
                    "url": final_url,
                    "duration_seconds": actual_duration or target_duration,
                    "requested_duration_seconds": target_duration,
                    "avatar_id": avatar_id,
                    "voice_id": voice_id,
                    "video_id": video_id,
                    "heygen_subtitle_url": poll_meta.get("subtitle_url"),
                    "subtitle_source": (
                        "heygen_srt" if poll_meta.get("subtitle_url") else "script_aligned"
                    ),
                }
        except httpx.HTTPStatusError as exc:
            return _fail(_parse_heygen_error(exc))
        except Exception as exc:
            logger.exception("HeyGen video failed: %s", exc)
            return _fail(humanize_http_error(exc))

    async def _generate_with_v3_primary(
        self,
        client: httpx.AsyncClient,
        base: str,
        headers: dict[str, str],
        *,
        brief: dict,
        copy: dict,
        avatar_id: str,
        voice_id: str,
        script: str,
        production_skeleton: str,
        format_type: str,
        target_duration: int,
    ) -> tuple[str, float | None, str, str, dict]:
        """v3 Video Agent — dynamic backgrounds, B-roll, multi-scene (HeyGen recommended)."""
        try:
            return await self._generate_v3_video_agent(
                client,
                base,
                headers,
                avatar_id=avatar_id,
                voice_id=voice_id,
                script=script,
                production_skeleton=production_skeleton,
                format_type=format_type,
                brief=brief,
                copy=copy,
                target_duration=target_duration,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code in (402, 403):
                raise
            err_preview = exc.response.text[:200] if exc.response else str(exc)
            catalog_avatar = str(brief.get("heygen_avatar_id") or "")
            if _is_public_heygen_look_id(catalog_avatar):
                raise ValueError(
                    f"HeyGen Video Agent failed ({err_preview}). "
                    "If you use Vespri, keep group id "
                    "25777ee579284b9d9081bc95c49c5f00 in .env and restart the backend."
                ) from exc
            logger.warning(
                "HeyGen v3 Video Agent failed (%s), falling back to v2 avatar",
                err_preview,
            )
        except (ValueError, TimeoutError) as exc:
            if _is_public_heygen_look_id(str(brief.get("heygen_avatar_id") or "")):
                raise
            logger.warning("HeyGen v3 Video Agent failed (%s), falling back to v2 avatar", exc)

        url, dur, vid, mode, meta = await self._generate_v2_avatar(
            client,
            base,
            headers,
            brief=brief,
            copy=copy,
            avatar_id=avatar_id,
            voice_id=voice_id,
            script=script,
            production_skeleton=production_skeleton,
            format_type=format_type,
            target_duration=target_duration,
        )
        return url, dur, vid, mode, meta

    async def _generate_v3_video_agent(
        self,
        client: httpx.AsyncClient,
        base: str,
        headers: dict[str, str],
        *,
        avatar_id: str,
        voice_id: str,
        script: str,
        production_skeleton: str,
        format_type: str,
        brief: dict,
        copy: dict,
        target_duration: int,
    ) -> tuple[str, float | None, str, str, dict]:
        """
        POST /v3/video-agents — create from prompt (see HeyGen quick start).
        GET /v3/videos/{video_id} — poll until completed.
        """
        agent_prompt = build_heygen_agent_prompt(
            brief=brief,
            copy=copy,
            format_type=format_type,
            duration=target_duration,
            avatar_id=avatar_id,
            voice_id=voice_id,
            spoken_script=script,
            production_skeleton=production_skeleton,
        )
        agent_prompt = clamp_heygen_v3_prompt(agent_prompt)
        if len(agent_prompt) > HEYGEN_V3_PROMPT_MAX:
            raise ValueError(
                f"HeyGen prompt still exceeds {HEYGEN_V3_PROMPT_MAX} characters after trimming"
            )
        logger.info(
            "HeyGen v3 Video Agent: %ss %s avatar=%s prompt_chars=%s",
            target_duration,
            format_type,
            avatar_id[:12],
            len(agent_prompt),
        )
        orientation = _heygen_v3_orientation(format_type, brief)
        payload: dict = {
            "prompt": agent_prompt,
            "avatar_id": avatar_id,
            "voice_id": voice_id,
            "orientation": orientation,
        }
        stats_urls = resolve_stats_image_urls(brief)
        if stats_urls:
            logger.info(
                "HeyGen v3: %s stats image(s) — post-process ffmpeg overlay (not attached to agent)",
                len(stats_urls),
            )
        # NOTE: HeyGen v3 Video Agent (/v3/video-agents) does NOT accept a
        # `caption` field — only /v3/videos (direct video) does.
        # Adding it causes "Extra inputs are not permitted" and video failure.
        create_resp = await self._heygen_request(
            client,
            "POST",
            f"{base}/v3/video-agents",
            headers=headers,
            json=payload,
            label="HeyGen v3 create",
        )
        create_resp.raise_for_status()
        created = create_resp.json().get("data") or {}
        session_id, video_id = _parse_v3_agent_create_response(created)
        if session_id and not video_id:
            logger.info("HeyGen v3 Video Agent session=%s — waiting for video_id", session_id[:20])
            video_id = await self._poll_v3_session_for_video_id(
                client, base, headers, session_id
            )
        if not video_id:
            raise ValueError(f"HeyGen v3 did not return video_id: {created}")
        url, duration, poll_meta = await self._poll_v3_status(
            client,
            base,
            headers,
            video_id,
            max_wait_seconds=settings.HEYGEN_V3_POLL_MAX_WAIT_SECONDS,
        )
        return url, duration, video_id, "v3_video_agent", poll_meta

    async def _generate_v2_avatar(
        self,
        client: httpx.AsyncClient,
        base: str,
        headers: dict[str, str],
        *,
        brief: dict,
        copy: dict,
        avatar_id: str,
        voice_id: str,
        script: str,
        production_skeleton: str,
        format_type: str,
        target_duration: int,
    ) -> tuple[str, float | None, str, str, dict]:
        """v2 — talking head on solid color only (legacy; looks more 'AI studio')."""
        dims = _video_dimensions(format_type, brief)
        bg_color = "#000000"
        if format_type in {"reel", "video", "stories"}:
            bg_color = str(brief.get("secondary_color") or "#000000")

        payload: dict = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "avatar_style": "normal",
                    },
                    "voice": {
                        "type": "text",
                        "input_text": script,
                        "voice_id": voice_id,
                    },
                    "background": {"type": "color", "value": bg_color},
                }
            ],
            "dimension": dims,
            # caption with style="default" burns captions into v2 videos
            "caption": {"file_format": "srt", "style": "default"},
        }
        create_resp = await self._heygen_request(
            client,
            "POST",
            f"{base}/v2/video/generate",
            headers=headers,
            json=payload,
            label="HeyGen v2 create",
        )
        if create_resp.status_code in (402, 403):
            create_resp.raise_for_status()

        if create_resp.status_code >= 400:
            logger.warning(
                "HeyGen v2 generate failed (%s), trying v3 Video Agent",
                create_resp.text[:200],
            )
            return await self._generate_v3_video_agent(
                client,
                base,
                headers,
                avatar_id=avatar_id,
                voice_id=voice_id,
                script=script,
                production_skeleton=production_skeleton,
                format_type=format_type,
                brief=brief,
                copy=copy,
                target_duration=target_duration,
            )

        create_resp.raise_for_status()
        data = create_resp.json().get("data") or {}
        video_id = data.get("video_id")
        if not video_id:
            raise ValueError("HeyGen v2 did not return video_id")

        url, duration, poll_meta = await self._poll_v1_status(
            client,
            base,
            headers,
            video_id,
            max_wait_seconds=settings.HEYGEN_V1_POLL_MAX_WAIT_SECONDS,
        )
        return url, duration, video_id, "v2_avatar", poll_meta

    async def _heygen_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        label: str,
        max_attempts: int | None = None,
        max_delay_sec: float | None = None,
        **kwargs,
    ) -> httpx.Response:
        return await async_request_with_retry(
            client,
            method,
            url,
            max_attempts=max_attempts or settings.HEYGEN_HTTP_RETRY_ATTEMPTS,
            base_delay_sec=settings.HEYGEN_HTTP_RETRY_BASE_SEC,
            max_delay_sec=max_delay_sec or 30.0,
            label=label,
            **kwargs,
        )

    async def _poll_v3_session_for_video_id(
        self,
        client: httpx.AsyncClient,
        base: str,
        headers: dict[str, str],
        session_id: str,
        *,
        max_wait_seconds: int | None = None,
    ) -> str:
        """Video Agent may return session_id before video_id exists."""
        deadline = time.monotonic() + (
            max_wait_seconds or min(900, settings.HEYGEN_V3_POLL_MAX_WAIT_SECONDS)
        )
        started = time.monotonic()
        while time.monotonic() < deadline:
            resp = await self._heygen_request(
                client,
                "GET",
                f"{base}/v3/video-agents/{session_id}",
                headers=headers,
                label="HeyGen v3 session",
                max_attempts=3,
                max_delay_sec=12.0,
            )
            resp.raise_for_status()
            data = resp.json().get("data") or resp.json()
            if not isinstance(data, dict):
                data = {}
            status = (data.get("status") or "").lower()
            video_id = data.get("video_id")
            if video_id:
                logger.info(
                    "HeyGen session %s → video_id=%s (%.0fs)",
                    session_id[:16],
                    str(video_id)[:16],
                    time.monotonic() - started,
                )
                return str(video_id)
            if status in _V3_FAIL_STATUSES:
                err = data.get("error") or data.get("message") or "HeyGen Video Agent failed"
                raise ValueError(str(err))
            logger.info(
                "HeyGen session %s status=%s (waiting for video_id, %.0fs)",
                session_id[:16],
                status or "unknown",
                time.monotonic() - started,
            )
            await asyncio.sleep(8)
        raise TimeoutError(
            f"HeyGen Video Agent session timed out waiting for video_id (session={session_id})"
        )

    async def _poll_v1_status(
        self,
        client: httpx.AsyncClient,
        base: str,
        headers: dict[str, str],
        video_id: str,
        *,
        max_wait_seconds: int = 1200,
    ) -> tuple[str, float | None, dict]:
        deadline = time.monotonic() + max_wait_seconds
        started = time.monotonic()
        poll_meta: dict = {}
        while time.monotonic() < deadline:
            resp = await self._heygen_request(
                client,
                "GET",
                f"{base}/v1/video_status.get",
                headers=headers,
                params={"video_id": video_id},
                label="HeyGen v1 poll",
                max_attempts=3,
                max_delay_sec=12.0,
            )
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            status = (data.get("status") or "").lower()
            if status in _V3_DONE_STATUSES or status == "completed":
                url = data.get("video_url")
                if not url:
                    raise ValueError("HeyGen completed without video_url")
                duration = data.get("duration")
                try:
                    duration_f = float(duration) if duration is not None else None
                except (TypeError, ValueError):
                    duration_f = None
                poll_meta = _poll_meta_from_data(data)
                return url, duration_f, poll_meta
            if status in _V3_FAIL_STATUSES or status == "failed":
                err = data.get("error") or data.get("message") or "HeyGen video failed"
                raise ValueError(err)
            poll_meta = _poll_meta_from_data(data)
            logger.info(
                "HeyGen v1 poll %s status=%s (%.0fs / %ss)",
                str(video_id)[:16],
                status or "unknown",
                time.monotonic() - started,
                max_wait_seconds,
            )
            await asyncio.sleep(8)
        raise TimeoutError(f"HeyGen video timed out after {max_wait_seconds}s (video_id={video_id})")

    async def _poll_v3_status(
        self,
        client: httpx.AsyncClient,
        base: str,
        headers: dict[str, str],
        video_id: str,
        *,
        max_wait_seconds: int = 3600,
    ) -> tuple[str, float | None, dict]:
        deadline = time.monotonic() + max_wait_seconds
        started = time.monotonic()
        last_status = ""
        poll_meta: dict = {}
        while time.monotonic() < deadline:
            resp = await self._heygen_request(
                client,
                "GET",
                f"{base}/v3/videos/{video_id}",
                headers=headers,
                label="HeyGen v3 poll",
                max_attempts=3,
                max_delay_sec=12.0,
            )
            resp.raise_for_status()
            data = resp.json().get("data") or resp.json()
            if not isinstance(data, dict):
                data = {}
            status = (data.get("status") or "").lower()
            if status != last_status:
                logger.info(
                    "HeyGen v3 poll %s status=%s (%.0fs / %ss)",
                    str(video_id)[:16],
                    status or "unknown",
                    time.monotonic() - started,
                    max_wait_seconds,
                )
                last_status = status
            if status in _V3_DONE_STATUSES:
                url = (
                    data.get("video_url")
                    or data.get("url")
                    or data.get("download_url")
                )
                if not url:
                    raise ValueError("HeyGen completed without video_url")
                duration = data.get("duration")
                try:
                    duration_f = float(duration) if duration is not None else None
                except (TypeError, ValueError):
                    duration_f = None
                poll_meta = _poll_meta_from_data(data)
                logger.info(
                    "HeyGen v3 done %s in %.0fs subs=%s",
                    str(video_id)[:16],
                    time.monotonic() - started,
                    "yes" if poll_meta.get("subtitle_url") else "no",
                )
                return url, duration_f, poll_meta
            if status in _V3_FAIL_STATUSES:
                err = (
                    data.get("failure_message")
                    or data.get("error")
                    or data.get("message")
                    or "HeyGen video failed"
                )
                if isinstance(err, dict):
                    err = err.get("message") or str(err)
                raise ValueError(str(err))
            await asyncio.sleep(10)
        raise TimeoutError(
            f"HeyGen video timed out after {max_wait_seconds}s (video_id={video_id}, last_status={last_status or 'unknown'})"
        )


def _parse_v3_agent_create_response(created: dict) -> tuple[str | None, str | None]:
    """Extract session_id and video_id from POST /v3/video-agents response."""
    session_id = created.get("session_id")
    video_id = created.get("video_id")
    raw_id = created.get("id")
    if raw_id:
        rid = str(raw_id)
        if rid.startswith("sess_"):
            session_id = session_id or rid
        elif not video_id:
            video_id = rid
    return (
        str(session_id) if session_id else None,
        str(video_id) if video_id else None,
    )


def _is_public_heygen_look_id(avatar_id: str) -> bool:
    """Hex look ids from app.heygen.com (e.g. Vespri) — v2 avatar API does not accept them."""
    raw = (avatar_id or "").strip()
    return bool(raw) and not raw.isdigit() and len(raw) >= 20


def _fail(error: str) -> dict:
    return {
        "status": "failed",
        "model": HEYGEN_MODEL_ID,
        "provider": "heygen",
        "url": None,
        "error": error,
    }


def _parse_heygen_error(exc: httpx.HTTPStatusError) -> str:
    detail = exc.response.text[:500] if exc.response is not None else str(exc)
    try:
        body = exc.response.json() if exc.response is not None else {}
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or detail
            if "10000 characters" in str(msg).lower():
                return (
                    "HeyGen video prompt was too long (max 10,000 characters). "
                    "Retry generation — the app now trims the script automatically. "
                    "If it persists, shorten Script/Brief Notes or Visual cues."
                )
            if "invalid avatar_id" in str(msg).lower() or "avatar not found" in str(msg).lower():
                return (
                    "HeyGen could not use that avatar id. For Vespri, use the group id from the "
                    "HeyGen URL (25777ee579284b9d9081bc95c49c5f00), restart the backend, and regenerate."
                )
            return msg
        return body.get("message") or detail
    except Exception:
        if "10000 characters" in detail.lower():
            return (
                "HeyGen video prompt was too long (max 10,000 characters). "
                "Retry generation after restarting the backend."
            )
        return detail or str(exc)
