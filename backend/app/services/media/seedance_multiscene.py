"""Plan and stitch multi-scene Seedance videos (up to 90s) via Higgsfield API."""

from __future__ import annotations

import logging
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
    resolve_higgsfield_video_duration,
    seedance_max_clip_seconds,
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
    if not is_seedance_job_set_type(job_set_type):
        return False
    target = min(max(2, int(requested_duration or 0)), SEEDANCE_MAX_TOTAL_SECONDS)
    return target > seedance_max_clip_seconds(job_set_type)


def plan_seedance_scenes(
    requested_duration: int,
    *,
    job_set_type: str,
    broll_raw: str = "",
) -> list[dict[str, Any]]:
    """Split target duration into <=max-clip scenes; map B-roll visuals by time range."""
    target = min(max(2, int(requested_duration or 0)), SEEDANCE_MAX_TOTAL_SECONDS)
    clip_cap = seedance_max_clip_seconds(job_set_type)
    segments = parse_scene_broll_directions(broll_raw, duration=target)

    scenes: list[dict[str, Any]] = []
    pos = 0.0
    while pos < target - 0.5:
        remaining = target - pos
        raw_dur = min(float(clip_cap), remaining)
        api_dur, _ = resolve_higgsfield_video_duration(job_set_type, int(round(raw_dur)))
        api_dur = max(2, min(api_dur, int(remaining)))
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
    """Per-scene motion prompt — uses B-roll visual when provided."""
    brand = brief.get("brand_name") or brief.get("product_name") or "brand"
    industry = brief.get("target_industry_label") or "business"
    ft = (format_type or "reel").lower()
    orient = "vertical 9:16" if ft in {"reel", "video", "stories"} else "landscape 16:9"
    dur = int(scene.get("duration") or 15)
    visual = str(scene.get("visual") or "").strip()
    label = str(scene.get("label") or "").strip()
    idx = int(scene.get("index") or 0) + 1

    if visual:
        scene_desc = f"{label}: {visual}" if label else visual
        prompt = (
            f"Scene {idx} of a {total_duration}s {orient} ad for {brand} ({industry}), "
            f"about {dur} seconds. "
            f"MANDATORY B-roll visual: {scene_desc}. "
            "Animate the seed image with subtle cinematic camera movement: slow push-in, "
            "gentle pan, or soft parallax. "
            f"Professional {industry} advertising look, warm natural lighting, "
            "realistic skin tones, shallow depth of field. "
            "CRITICAL: no on-screen text, captions, logos, or watermarks. "
            "No scene cuts within this clip; keep subject consistent with the seed image."
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
    from app.services.media.higgsfield_client_service import upload_local_image

    upload_root = Path(file_service.upload_dir)
    dest_dir = upload_root / tenant_id / "generated"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"seedance-frame-{uuid.uuid4()}.png"
    dest_path.write_bytes(png_bytes)
    return await upload_local_image(str(dest_path))


def concat_video_files(paths: list[Path], output_path: Path) -> None:
    """Concatenate MP4 clips; re-encode if stream-copy concat fails."""
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
        copy_cmd = [
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
            "-c",
            "copy",
            str(output_path),
        ]
        proc = subprocess.run(copy_cmd, capture_output=True, text=True)
        if proc.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 1024:
            return

        logger.warning(
            "Stream-copy concat failed (%s); re-encoding",
            (proc.stderr or proc.stdout or "")[:200],
        )
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
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        proc2 = subprocess.run(reencode_cmd, capture_output=True, text=True)
        if proc2.returncode != 0 or not output_path.is_file():
            raise RuntimeError(
                f"Failed to stitch Seedance clips: {(proc2.stderr or proc2.stdout or '')[:400]}"
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
