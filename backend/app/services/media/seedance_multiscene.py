"""Plan and stitch multi-scene Seedance videos (up to 90s) via Higgsfield API."""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from app.services.ffmpeg_util import probe_video_duration, require_ffmpeg
from app.services.file_service import file_service
from app.services.media.higgsfield_models import (
    SEEDANCE_JOB_TYPES,
    SEEDANCE_MAX_TOTAL_SECONDS,
    DOP_STITCH_CLIP_SECONDS,
    resolve_higgsfield_video_duration,
    seedance_max_clip_seconds,
    supports_dop_clip_stitch,
)
from app.services.video_script_skeleton import (
    _heygen_scene_broll_raw,
    _visual_for_time_range,
    parse_scene_broll_directions,
)

logger = logging.getLogger(__name__)


def is_seedance_job_set_type(job_set_type: str | None) -> bool:
    return (job_set_type or "").lower() in SEEDANCE_JOB_TYPES


def seedance_multiscene_requested(job_set_type: str, requested_duration: int) -> bool:
    """True when we should generate multiple clips and ffmpeg-stitch them."""
    from app.services.media.higgsfield_models import VIDEO_CLIP_STITCH_ENABLED

    if not VIDEO_CLIP_STITCH_ENABLED:
        return False
    if not supports_dop_clip_stitch(job_set_type):
        return False
    target = min(max(2, int(requested_duration or 0)), SEEDANCE_MAX_TOTAL_SECONDS)
    return target > seedance_max_clip_seconds(job_set_type)


def parse_timed_beats_from_prompt(prompt: str, total_duration: int) -> list[dict[str, Any]]:
    """
    Extract HOOK / BODY / CLOSE (or CLIP 1/2/3) beats from a Creative Studio prompt
    into time-ranged visuals for stitch planning.
    """
    text = (prompt or "").strip()
    if not text:
        return []
    total = max(5, int(total_duration or 15))
    patterns = [
        (
            "hook",
            re.compile(
                r"(?is)\bHOOK\s*(?:\([^)]*\))?\s*:?\s*(.+?)(?=\b(?:BODY|CLOSE|CTA|CLIP\s*2)\b|$)"
            ),
        ),
        (
            "body",
            re.compile(
                r"(?is)\bBODY\s*(?:\([^)]*\))?\s*:?\s*(.+?)(?=\b(?:CLOSE|CTA|CLIP\s*3)\b|$)"
            ),
        ),
        (
            "close",
            re.compile(
                # Colon required so "close-up" does not match
                r"(?is)\b(?:CLOSE|CTA)\s*(?:\([^)]*\))?\s*:\s*(.+?)(?=\b(?:CRITICAL|STRICT|VISUAL STYLE|EDITING)\b|$)"
            ),
        ),
    ]
    found: list[tuple[str, str]] = []
    for label, rx in patterns:
        m = rx.search(text)
        if m:
            chunk = re.sub(r"\s+", " ", m.group(1)).strip(" :-")
            chunk = re.sub(r"(?i)\b(?:CRITICAL|STRICT NEGATIVE).*$", "", chunk).strip()
            if len(chunk) >= 12:
                found.append((label, chunk[:900]))

    # CLIP 1 / CLIP 2 / CLIP 3 — supports "CLIP 1 — 0–5 SECONDS: …"
    clip_rx = re.compile(
        r"(?is)\bCLIP\s*(\d+)\s*"
        r"(?:[—–\-]\s*)?(?:\d+\s*[–\-]\s*\d+\s*(?:SECONDS?|s)\s*)?"
        r"(?:\([^)]*\))?\s*:?\s*"
        r"(.+?)(?=\bCLIP\s*\d+\b|\b(?:CRITICAL|STRICT|VISUAL STYLE|EDITING / TIMING)\b|$)"
    )
    clips = []
    for m in clip_rx.finditer(text):
        chunk = re.sub(r"\s+", " ", m.group(2)).strip(" :-")
        # Drop trailing section headers if they leaked in
        chunk = re.sub(
            r"(?i)\b(?:VISUAL STYLE|EDITING / TIMING|STRICT NEGATIVE).*$",
            "",
            chunk,
        ).strip()
        if len(chunk) >= 8:
            clips.append((f"clip_{m.group(1)}", chunk[:900]))
    if len(clips) >= 2:
        found = clips

    if len(found) < 2:
        return []

    n = len(found)
    seg_len = total / n
    out: list[dict[str, Any]] = []
    for i, (label, visual) in enumerate(found):
        start = i * seg_len
        end = total if i == n - 1 else (i + 1) * seg_len
        out.append(
            {
                "start": float(start),
                "end": float(end),
                "label": label.upper().replace("_", " "),
                "visual": visual,
            }
        )
    return out


def plan_seedance_scenes(
    requested_duration: int,
    *,
    job_set_type: str,
    broll_raw: str = "",
    scene_prompt: str = "",
) -> list[dict[str, Any]]:
    """Split target duration into <=max-clip scenes; map B-roll / timed beats by range."""
    target = min(max(2, int(requested_duration or 0)), SEEDANCE_MAX_TOTAL_SECONDS)
    clip_cap = seedance_max_clip_seconds(job_set_type)
    segments = parse_scene_broll_directions(broll_raw, duration=target)
    if not segments and scene_prompt:
        segments = parse_timed_beats_from_prompt(scene_prompt, target)

    # If the user wrote CLIP 1/2/3 (or HOOK/BODY/CLOSE), honor that beat count
    # so a 15s prompt becomes three ~5s clips matching the script.
    if segments and len(segments) >= 2:
        scenes: list[dict[str, Any]] = []
        for i, seg in enumerate(segments):
            start = float(seg["start"])
            end = float(seg["end"])
            raw = max(2, int(round(end - start)))
            api_dur, _ = resolve_higgsfield_video_duration(job_set_type, raw)
            dur = max(2, min(int(api_dur), int(clip_cap), raw))
            scenes.append(
                {
                    "index": i,
                    "start": start,
                    "end": start + dur,
                    "duration": dur,
                    "visual": seg.get("visual"),
                    "label": seg.get("label"),
                }
            )
        return scenes

    scenes = []
    pos = 0.0
    while pos < target - 0.5:
        remaining = target - pos
        raw_dur = min(float(clip_cap), remaining)
        api_dur, _ = resolve_higgsfield_video_duration(job_set_type, int(round(raw_dur)))
        api_dur = max(2, min(int(api_dur), int(remaining), int(clip_cap)))
        if remaining < api_dur and remaining >= 2:
            api_dur = max(2, int(round(remaining)))
        start = pos
        end = min(float(target), pos + api_dur)
        dur = max(2, int(round(end - start)))
        visual = (
            _visual_for_time_range(start, end, segments) if segments else None
        )
        label = None
        if segments:
            mid = (start + end) / 2.0
            for seg in segments:
                if float(seg["start"]) <= mid < float(seg["end"]):
                    label = seg.get("label")
                    break
        scenes.append(
            {
                "index": len(scenes),
                "start": start,
                "end": start + dur,
                "duration": dur,
                "visual": visual,
                "label": label,
            }
        )
        pos += dur

    total = sum(s["duration"] for s in scenes)
    if total > target and scenes:
        overflow = total - target
        scenes[-1]["duration"] = max(2, scenes[-1]["duration"] - overflow)
        scenes[-1]["end"] = scenes[-1]["start"] + scenes[-1]["duration"]

    return scenes


def build_seedance_scene_prompt(
    scene: dict[str, Any],
    *,
    brief: dict,
    copy: dict,
    format_type: str,
    production_skeleton: str,
    total_duration: int,
) -> str:
    """Per-scene motion prompt — uses B-roll / timed beat visual when provided."""
    brand = brief.get("brand_name") or brief.get("product_name") or "brand"
    industry = brief.get("target_industry_label") or "business"
    ft = (format_type or "reel").lower()
    orient = "vertical 9:16" if ft in {"reel", "video", "stories"} else "landscape 16:9"
    dur = int(scene.get("duration") or DOP_STITCH_CLIP_SECONDS)
    visual = str(scene.get("visual") or "").strip()
    label = str(scene.get("label") or "").strip()
    idx = int(scene.get("index") or 0) + 1
    base_prompt = str(
        brief.get("creative_studio_prompt")
        or production_skeleton
        or ""
    ).strip()

    if visual:
        scene_desc = f"{label}: {visual}" if label else visual
        prompt = (
            f"Scene {idx} of a {total_duration}s {orient} commercial for {brand}, "
            f"exactly ~{dur} seconds, ONE continuous shot. "
            f"THIS CLIP ONLY — follow this action precisely: {scene_desc}. "
            "FULL FRAME single camera shot — NO split screen, NO collage, NO stacked frames, "
            "NO picture-in-picture, NO dual panels. "
            "Animate naturally from the seed: product and talent stay consistent. "
            "CRITICAL: no on-screen text, captions, logos, or watermarks."
        )
        from app.services.brand_prompt import clamp_runway_image_prompt
        from app.services.video_script_skeleton import RUNWAY_VIDEO_PROMPT_MAX

        return clamp_runway_image_prompt(prompt, max_len=RUNWAY_VIDEO_PROMPT_MAX)

    # Fall back: slice the full Creative Studio prompt into this beat window
    if base_prompt:
        start = float(scene.get("start") or 0)
        end = float(scene.get("end") or (start + dur))
        prompt = (
            f"Scene {idx}/{max(1, int(round(total_duration / max(dur, 1))))} "
            f"({int(start)}-{int(end)}s of {total_duration}s) {orient}. "
            f"Animate ONLY this beat for ~{dur}s, continuous motion from the seed frame. "
            f"Overall scene: {base_prompt[:700]}. "
            "Keep subject/product/setting consistent. "
            "CRITICAL: no on-screen text, captions, logos, or watermarks."
        )
        from app.services.brand_prompt import clamp_runway_image_prompt
        from app.services.video_script_skeleton import RUNWAY_VIDEO_PROMPT_MAX

        return clamp_runway_image_prompt(prompt, max_len=RUNWAY_VIDEO_PROMPT_MAX)

    hook = copy.get("hook") or ""
    base = (
        f"Scene {idx} of a {total_duration}s {orient} ad for {brand} ({industry}), "
        f"about {dur} seconds. "
        f"Professional {industry} advertising look, warm natural lighting, "
        "realistic skin tones, shallow depth of field. "
        "CRITICAL: no on-screen text, captions, logos, or watermarks. "
        "No scene cuts within this clip; single continuous motion."
    )
    if idx == 1 and hook:
        base += f" Opening energy: {hook[:200]}."
    return base


def extract_last_frame_png(video_path: Path) -> bytes | None:
    from app.services.video_portrait import _extract_png_frame

    ffmpeg = require_ffmpeg()
    duration = probe_video_duration(video_path)
    at = max(0.1, (duration or 5.0) - 0.15)
    return _extract_png_frame(ffmpeg, video_path, seconds=at)


async def upload_frame_png(png_bytes: bytes, *, tenant_id: str) -> str:
    """Upload a video last-frame as JPEG to Higgsfield (for stitch continuity)."""
    from app.services.media.higgsfield_client_service import (
        png_bytes_to_jpeg,
        upload_bytes,
        upload_local_image,
    )

    upload_root = Path(file_service.upload_dir)
    dest_dir = upload_root / tenant_id / "generated"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Prefer JPEG upload — PNG presigned PUTs often 403 on Higgsfield S3.
    try:
        jpeg = png_bytes_to_jpeg(png_bytes)
        dest_jpg = dest_dir / f"seedance-frame-{uuid.uuid4()}.jpg"
        dest_jpg.write_bytes(jpeg)
        return await upload_bytes(jpeg, content_type="image/jpeg")
    except Exception as exc:
        logger.warning("JPEG frame upload failed (%s); trying PNG file path", exc)
        dest_path = dest_dir / f"seedance-frame-{uuid.uuid4()}.png"
        dest_path.write_bytes(png_bytes)
        return await upload_local_image(str(dest_path))


def concat_video_files(paths: list[Path], output_path: Path) -> None:
    """Concatenate MP4 clips with re-encode (stream-copy often yields wrong duration)."""
    if not paths:
        raise ValueError("No video clips to concatenate")
    if len(paths) == 1:
        output_path.write_bytes(paths[0].read_bytes())
        return

    ffmpeg = require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
        encoding="utf-8",
    ) as list_file:
        for p in paths:
            escaped = str(p.resolve()).replace("'", "'\\''")
            list_file.write(f"file '{escaped}'\n")
        list_path = Path(list_file.name)

    try:
        # Always re-encode so durations add correctly across Higgsfield clips
        reencode_cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        proc2 = subprocess.run(reencode_cmd, capture_output=True, text=True)
        if proc2.returncode != 0 or not output_path.is_file():
            raise RuntimeError(
                f"Failed to stitch video clips: {(proc2.stderr or proc2.stdout or '')[:400]}"
            )
    finally:
        list_path.unlink(missing_ok=True)


def trim_video_to_duration(video_path: Path, max_seconds: float) -> Path | None:
    """Trim stitched video if slightly longer than target."""
    probed = probe_video_duration(video_path)
    if probed is None or probed <= max_seconds + 0.35:
        return None
    ffmpeg = require_ffmpeg()
    trimmed = video_path.with_name(f"{video_path.stem}-trim{video_path.suffix}")
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-t",
        str(max_seconds),
        "-c",
        "copy",
        str(trimmed),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0 and trimmed.is_file():
        return trimmed
    return None


def scene_broll_from_brief(brief: dict) -> str:
    return _heygen_scene_broll_raw(brief)
