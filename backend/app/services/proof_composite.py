"""
Proof composite — replace a video segment's frames with a static PNG,
while preserving the original audio track exactly.

Used for "proof-first" ad workflows where Scene 1 / Scene 2 are placeholder
charcoal plates that the app replaces with the client's uploaded stat screenshots.

FFmpeg command overview:
  Input 0: the generated charcoal placeholder video (has audio)
  Input 1: the proof PNG image

  Filter graph:
    1. Scale proof PNG to exactly W×H (aspect-fit, pad charcoal where needed)
    2. Loop the scaled still for the full duration of input 0
    3. Pass audio from input 0 unchanged
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _download_url(url: str, suffix: str = ".mp4") -> Path:
    tmp = Path(tempfile.mktemp(suffix=suffix))
    from app.services.logo_overlay import file_url_to_local_path

    local = file_url_to_local_path(url)
    if local:
        shutil.copyfile(local, tmp)
    else:
        urllib.request.urlretrieve(url, tmp)
    return tmp


def composite_proof_windows(
    *,
    video_url: str,
    proof_assets: list[dict[str, Any]],
    proof_scenes: list[dict[str, Any]],
    tenant_id: str,
    canvas_size: int = 1080,
    pad_color: str = "0x1A1C20",
) -> tuple[str, int]:
    """Replace selected time windows with exact uploaded proof images.

    The underlying video's audio is retained. Proof images are scaled to fit a
    square charcoal canvas and are never sent through a generative model.
    """
    if not video_url or not proof_assets or not proof_scenes:
        return video_url, 0

    from app.services.ffmpeg_util import require_ffmpeg
    from app.services.file_service import file_service

    ffmpeg = require_ffmpeg()
    video_tmp = _download_url(video_url, ".mp4")
    image_tmps: list[Path] = []
    output_tmp = Path(tempfile.mktemp(suffix=".mp4"))
    try:
        windows: list[tuple[Path, float, float]] = []
        for idx, scene in enumerate(proof_scenes):
            if idx >= len(proof_assets):
                break
            proof_url = str(proof_assets[idx].get("url") or "").strip()
            start = max(0.0, float(scene.get("start") or 0.0))
            end = max(start, float(scene.get("end") or start))
            if not proof_url or end - start < 0.05:
                continue
            suffix = ".png" if ".png" in proof_url.lower() else ".jpg"
            image_tmp = _download_url(proof_url, suffix)
            image_tmps.append(image_tmp)
            windows.append((image_tmp, start, end))
        if not windows:
            return video_url, 0

        command = [ffmpeg, "-y", "-i", str(video_tmp)]
        for image_tmp, _, _ in windows:
            command.extend(["-loop", "1", "-i", str(image_tmp)])

        filters: list[str] = [
            f"[0:v]scale={canvas_size}:{canvas_size}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={canvas_size}:{canvas_size}:(ow-iw)/2:(oh-ih)/2:"
            f"color={pad_color},setsar=1[proofbase]"
        ]
        current = "proofbase"
        for idx, (_, start, end) in enumerate(windows, 1):
            proof_label = f"proof{idx}"
            output_label = f"proofout{idx}"
            filters.append(
                f"[{idx}:v]scale={canvas_size}:{canvas_size}:"
                "force_original_aspect_ratio=decrease,"
                f"pad={canvas_size}:{canvas_size}:(ow-iw)/2:(oh-ih)/2:"
                f"color={pad_color},setsar=1[{proof_label}]"
            )
            # End is exclusive so adjacent proof cards switch cleanly on the
            # authored boundary without a one-frame overlap.
            filters.append(
                f"[{current}][{proof_label}]overlay=0:0:"
                f"enable='gte(t,{start:.3f})*lt(t,{end:.3f})'[{output_label}]"
            )
            current = output_label

        duration = _video_duration(ffmpeg, video_tmp)
        command.extend([
            "-filter_complex", ";".join(filters),
            "-map", f"[{current}]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-t", f"{duration:.3f}",
            "-movflags", "+faststart", str(output_tmp),
        ])
        proc = subprocess.run(command, capture_output=True, text=True)
        # Very short/static proof videos compress exceptionally well, so file
        # size is not a reliable success threshold. FFmpeg's exit status plus a
        # minimally valid MP4 is enough here; duration is verified separately.
        if proc.returncode or not output_tmp.is_file() or output_tmp.stat().st_size < 1_000:
            raise RuntimeError(
                "proof window composite failed: " + str(proc.stderr or "")[-1200:]
            )
        saved = file_service.save_bytes(
            content=output_tmp.read_bytes(),
            tenant_id=tenant_id,
            subfolder="generated",
            suffix=".mp4",
            content_type="video/mp4",
        )
        return str(saved["file_url"]), len(windows)
    finally:
        video_tmp.unlink(missing_ok=True)
        output_tmp.unlink(missing_ok=True)
        for path in image_tmps:
            path.unlink(missing_ok=True)


def composite_proof_over_video(
    *,
    video_url: str,
    proof_image_url: str,
    output_path: Path,
    canvas_size: int = 1080,
    pad_color: str = "0x1A1C20",
) -> Path:
    """
    Download the charcoal placeholder video and the proof PNG, then produce
    an output video where every frame is the proof PNG aspect-fit inside the
    canvas, with the original audio track kept intact.

    Returns the output_path on success.
    """
    from app.services.ffmpeg_util import require_ffmpeg

    ffmpeg = require_ffmpeg()

    video_tmp = _download_url(video_url, ".mp4")
    img_ext = ".png" if ".png" in proof_image_url.lower() else ".jpg"
    img_tmp = _download_url(proof_image_url, img_ext)

    try:
        W = canvas_size
        H = canvas_size
        # Scale proof to fit inside W×H, pad with charcoal
        filter_complex = (
            f"[1:v]"
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={pad_color},"
            f"loop=loop=-1:size=1:start=0,"
            f"fps=24,"
            f"trim=duration={_video_duration(ffmpeg, video_tmp):.3f},"
            f"setpts=PTS-STARTPTS"
            f"[still]"
        )
        cmd = [
            ffmpeg, "-y",
            "-i", str(video_tmp),          # input 0: original video (for audio + duration)
            "-loop", "1",
            "-i", str(img_tmp),            # input 1: proof PNG
            "-filter_complex", filter_complex,
            "-map", "[still]",
            "-map", "0:a?",               # keep original audio unchanged
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-shortest",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"proof_composite ffmpeg failed:\n{proc.stderr[-1200:]}"
            )
        logger.info("Proof composite done → %s", output_path)
        return output_path
    finally:
        video_tmp.unlink(missing_ok=True)
        img_tmp.unlink(missing_ok=True)


def _video_duration(ffmpeg: str, video_path: Path) -> float:
    """Read the real input duration; never shorten proof output on probe failure."""
    del ffmpeg
    from app.services.ffmpeg_util import probe_video_duration

    duration = probe_video_duration(video_path)
    if duration is None or duration <= 0:
        raise RuntimeError("Cannot determine source video duration for proof compositing")
    return float(duration)


def apply_proof_composites(
    *,
    tenant_id: str,
    session_id: str,
    proof_assets: list[dict[str, Any]],
    scene_plan: list[dict[str, Any]],
    video_segments: list[dict[str, Any]],
    upload_dir: str,
) -> list[dict[str, Any]]:
    """
    For each scene marked type='proof', if a matching video segment exists,
    replace its frames with the corresponding proof PNG.

    proof_assets: [{"url": "...", "label": "proof", "scene": 1}, ...]
    scene_plan:   parsed scene list from parse_scene_plan()
    video_segments: [{"scene": 1, "video_url": "...", "audio_url": "..."}, ...]

    Returns updated video_segments list with proof_url set on composited scenes.
    """
    proof_scenes = [s for s in scene_plan if s.get("type") == "proof"]
    if not proof_scenes or not proof_assets:
        return video_segments

    root = Path(upload_dir) / tenant_id / "creative-studio-proof-composites"
    root.mkdir(parents=True, exist_ok=True)

    updated = list(video_segments)
    for i, seg in enumerate(updated):
        scene_num = int(seg.get("scene") or 0)
        proof_scene = next((s for s in proof_scenes if s.get("scene") == scene_num), None)
        if not proof_scene:
            continue
        # Pick the proof asset by order (proof 1 → scene 1, proof 2 → scene 2)
        proof_idx = proof_scenes.index(proof_scene)
        if proof_idx >= len(proof_assets):
            continue
        proof_url = str(proof_assets[proof_idx].get("url") or "").strip()
        video_url = str(seg.get("video_url") or seg.get("url") or "").strip()
        if not proof_url or not video_url:
            continue

        out_path = root / f"scene_{scene_num}_proof_composite.mp4"
        try:
            composite_proof_over_video(
                video_url=video_url,
                proof_image_url=proof_url,
                output_path=out_path,
            )
            updated[i] = {**seg, "video_url": out_path.as_uri(), "proof_composited": True}
            logger.info("Scene %d → proof composite applied", scene_num)
        except Exception as exc:
            logger.error("Proof composite failed for scene %d: %s", scene_num, exc)

    return updated
