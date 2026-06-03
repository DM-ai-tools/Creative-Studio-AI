"""Generate voiceover (Runway ElevenLabs TTS) and mux onto ad videos."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.cta_defaults import resolve_campaign_cta
from app.services.copy_helpers import texts_duplicate
from app.services.file_service import file_service
from app.services.logo_overlay import file_url_to_local_path
from app.services.media.runway_client import runway_headers, runway_base_url, submit_task, wait_for_task_output

logger = logging.getLogger(__name__)

RUNWAY_TTS_MAX_CHARS = 1000
DEFAULT_VOICE_PRESET = "Serene"
HIGGSFIELD_VOICE_PRESET_MAP: dict[str, str] = {
    "serene_female": "Serene",
    "deep_male": "Gravelly",
    "clear_female": "Bright",
    "warm_male": "Calm",
}


def build_voiceover_script(*, copy: dict, brief: dict) -> str:
    """Short spoken script from production skeleton, then variant copy."""
    from app.services.video_duration import resolve_video_duration_seconds
    from app.services.video_script_skeleton import (
        extract_heygen_spoken_script,
        is_pdf_script_mode,
        resolve_heygen_spoken_script,
    )

    kb = brief.get("key_benefits")
    if isinstance(kb, dict):
        skeleton = kb.get("video_script_skeleton") or brief.get("video_script_skeleton")
        if skeleton and str(skeleton).strip():
            duration = resolve_video_duration_seconds(brief)
            if is_pdf_script_mode(brief):
                spoken = resolve_heygen_spoken_script(
                    brief,
                    copy,
                    production_skeleton=str(skeleton),
                    target_seconds=duration,
                )
            else:
                spoken = extract_heygen_spoken_script(
                    str(skeleton), target_seconds=duration
                )
            if spoken.strip():
                script = spoken.replace("—", ", ").replace("–", ", ").replace("  ", " ").strip()
                if len(script) > RUNWAY_TTS_MAX_CHARS:
                    script = script[: RUNWAY_TTS_MAX_CHARS - 1].rsplit(" ", 1)[0] + "."
                return script

    hook = str(copy.get("hook") or "").strip()
    headline = str(copy.get("headline") or "").strip()
    cta = str(copy.get("cta") or resolve_campaign_cta(brief) or "Learn more").strip()

    sentences: list[str] = []
    if hook and not texts_duplicate(hook, headline):
        sentences.append(hook.rstrip(".") + ".")
    if headline:
        sentences.append(headline.rstrip(".") + ".")
    if cta:
        cta_spoken = cta if cta.endswith((".", "!", "?")) else f"{cta}."
        if not any(texts_duplicate(cta_spoken, s) for s in sentences):
            sentences.append(cta_spoken)

    if not sentences:
        campaign = brief.get("campaign_product") or brief.get("product_name") or "our offer"
        closing = cta if cta.endswith((".", "!", "?")) else (f"{cta}." if cta else "Learn more.")
        sentences.append(f"Discover {campaign}. {closing}")

    script = " ".join(sentences)
    script = script.replace("—", ", ").replace("–", ", ").replace("  ", " ").strip()
    if len(script) > RUNWAY_TTS_MAX_CHARS:
        script = script[: RUNWAY_TTS_MAX_CHARS - 1].rsplit(" ", 1)[0] + "."
    return script


def _ffmpeg_executable() -> str | None:
    from app.services.ffmpeg_util import ffmpeg_executable

    return ffmpeg_executable()


def mux_video_with_audio(*, video_path: Path, audio_path: Path, output_path: Path) -> None:
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Install ffmpeg or add imageio-ffmpeg to requirements.")

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-shortest",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed: {proc.stderr[-500:]}")


async def generate_tts_audio(
    client: httpx.AsyncClient,
    *,
    script: str,
    voice_preset: str | None = None,
) -> bytes:
    preset = (voice_preset or settings.RUNWAYML_VOICE_PRESET or DEFAULT_VOICE_PRESET).strip()
    payload = {
        "model": settings.RUNWAYML_TTS_MODEL,
        "promptText": script,
        "voice": {"type": "runway-preset", "presetId": preset},
    }
    task_id = await submit_task(client, "/text_to_speech", payload)
    outputs = await wait_for_task_output(client, task_id)
    audio_url = outputs[0]
    download_headers: dict[str, str] | None = None
    if "runwayml.com" in audio_url:
        download_headers = {"Authorization": f"Bearer {settings.RUNWAYML_API_KEY}"}
    response = await client.get(
        audio_url, follow_redirects=True, timeout=120.0, headers=download_headers
    )
    response.raise_for_status()
    content = response.content
    if len(content) < 32:
        raise ValueError("TTS download too small")
    return content


async def apply_voiceover_to_video_file(
    client: httpx.AsyncClient,
    video_file_url: str,
    *,
    copy: dict,
    brief: dict,
    tenant_id: str,
    script_override: str | None = None,
    voice_preset_override: str | None = None,
) -> dict:
    """Return {status, url?, script?, voice?, error?} after muxing voiceover onto video."""
    if not settings.RUNWAYML_VOICEOVER_ENABLED:
        return {"status": "skipped", "reason": "disabled"}

    video_path = file_url_to_local_path(video_file_url)
    if not video_path:
        return {"status": "failed", "error": "Video file not found for voiceover"}

    script = (script_override or "").strip() or build_voiceover_script(copy=copy, brief=brief)
    if not script.strip():
        return {"status": "failed", "error": "Empty voiceover script"}

    voice_preset = (
        (voice_preset_override or "").strip()
        or settings.RUNWAYML_VOICE_PRESET
        or DEFAULT_VOICE_PRESET
    )

    try:
        audio_bytes = await generate_tts_audio(client, script=script, voice_preset=voice_preset)
    except Exception as exc:
        logger.exception("Runway TTS failed: %s", exc)
        return {"status": "failed", "error": str(exc)[:240], "script": script}

    suffix = ".mp3"
    if audio_bytes[:4] == b"RIFF":
        suffix = ".wav"
    elif audio_bytes[4:8] == b"ftyp":
        suffix = ".m4a"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        audio_path = tmp_dir / f"vo{suffix}"
        audio_path.write_bytes(audio_bytes)
        out_path = tmp_dir / "muxed.mp4"
        try:
            mux_video_with_audio(video_path=video_path, audio_path=audio_path, output_path=out_path)
        except Exception as exc:
            logger.exception("Voiceover mux failed: %s", exc)
            return {"status": "failed", "error": str(exc)[:240], "script": script}

        muxed_bytes = out_path.read_bytes()
        saved = file_service.save_bytes(
            content=muxed_bytes,
            tenant_id=tenant_id,
            subfolder="generated",
            suffix=".mp4",
            content_type="video/mp4",
        )
        try:
            video_path.unlink(missing_ok=True)
        except OSError:
            pass

        return {
            "status": "done",
            "url": saved["file_url"],
            "script": script,
            "voice": voice_preset,
            "model": settings.RUNWAYML_TTS_MODEL,
        }
