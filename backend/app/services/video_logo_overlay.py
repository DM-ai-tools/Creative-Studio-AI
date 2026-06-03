"""Burn brand logo onto generated ad videos (Runway + HeyGen)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.config import settings
import io

from app.services.brand_logo import logo_local_path, resolve_video_logo_urls
from app.services.logo_overlay import _pick_logo_rgba_for_placement, _region_is_light
from app.services.ffmpeg_util import ffmpeg_executable, ffprobe_executable, require_ffmpeg
logger = logging.getLogger(__name__)


def _heygen_settings(brief: dict | None) -> dict:
    if not brief:
        return {}
    raw = brief.get("heygen_settings")
    if isinstance(raw, dict):
        return raw
    kb = brief.get("key_benefits")
    if isinstance(kb, dict) and isinstance(kb.get("heygen_settings"), dict):
        return kb["heygen_settings"]
    return {}


def video_logo_overlay_enabled(brief: dict | None) -> bool:
    """Honours HeyGen UI “Brand-styled overlay” (default on)."""
    heygen = _heygen_settings(brief)
    return heygen.get("brand_styled_overlay", True) is not False


def is_portrait_video_format(format_type: str | None, brief: dict | None = None) -> bool:
    """9:16 placements — logo bottom-right. Landscape `video` → top-left."""
    ft = (format_type or "").lower()
    if ft in {"reel", "stories"}:
        return True
    if ft == "video":
        return False
    heygen = _heygen_settings(brief)
    ar = str(
        heygen.get("aspect_ratio")
        or heygen.get("aspect_ratio_label")
        or heygen.get("aspect_ratio_custom")
        or ""
    ).lower()
    if "9:16" in ar or "9x16" in ar or "portrait" in ar:
        return True
    if "16:9" in ar or "16x9" in ar or "landscape" in ar:
        return False
    return ft not in {"video"}


def _ffprobe_executable() -> str | None:
    return ffprobe_executable()


def _video_dimensions(video_path: Path) -> tuple[int, int]:
    ffprobe = _ffprobe_executable()
    if not ffprobe:
        return 1080, 1920
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and "x" in proc.stdout:
        w, h = proc.stdout.strip().split("x", 1)
        return max(1, int(w)), max(1, int(h))
    return 1080, 1920


def _video_corner_is_light(
    video_path: Path,
    *,
    overlay_x: int,
    overlay_y: int,
    region_w: int,
    region_h: int,
) -> bool:
    """Sample a frame where the logo sits — pick white vs dark logo from Brand Kit."""
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        return False
    from app.services.video_portrait import _extract_png_frame

    for t in (0.8, 2.0, 4.0):
        raw = _extract_png_frame(ffmpeg, video_path, seconds=t)
        if not raw:
            continue
        from PIL import Image


        img = Image.open(io.BytesIO(raw)).convert("RGB")
        return _region_is_light(img, overlay_x, overlay_y, region_w, region_h)
    return False


def _logo_overlay_box(
    width: int,
    height: int,
    logo_path: Path,
    logo_w: int,
    format_type: str | None,
    brief: dict | None,
) -> tuple[int, int, int, int]:
    """Return overlay_x, overlay_y, logo_w, logo_h for placement + background sampling."""
    from PIL import Image

    pad = max(14, int(min(width, height) * 0.025))
    with Image.open(logo_path) as im:
        lw, lh = im.size
    logo_h = max(20, int(logo_w * lh / max(lw, 1)))

    if is_portrait_video_format(format_type, brief):
        overlay_x = max(pad, width - logo_w - pad)
        overlay_y = max(pad, height - logo_h - pad)
    else:
        overlay_x = pad
        overlay_y = pad
    return overlay_x, overlay_y, logo_w, logo_h


def _prepare_logo_png_for_video(
    video_path: Path,
    logo_path: Path,
    *,
    logo_on_light_path: Path | None,
    target_width: int,
    format_type: str | None = None,
    brief: dict | None = None,
) -> Path:
    """
    Brand Kit: primary logo on dark corners, on_light variant on bright corners.
    """
    from PIL import Image

    width, height = _video_dimensions(video_path)
    overlay_x, overlay_y, logo_w, logo_h = _logo_overlay_box(
        width, height, logo_path, target_width, format_type, brief
    )
    light_corner = _video_corner_is_light(
        video_path,
        overlay_x=overlay_x,
        overlay_y=overlay_y,
        region_w=logo_w + 8,
        region_h=logo_h + 8,
    )

    if light_corner and logo_on_light_path and logo_on_light_path.is_file():
        logger.info("Video logo: brand kit on_light (dark mark) — bright corner detected")
    elif light_corner:
        logger.info(
            "Video logo: brand kit primary on bright corner (upload on_light logo for best contrast)"
        )
    else:
        logger.info("Video logo: brand kit primary (light mark) — dark corner detected")

    logo = _pick_logo_rgba_for_placement(
        logo_path=logo_path,
        logo_on_light_path=logo_on_light_path,
        light_background=light_corner,
        max_width=target_width,
    )

    tmp = Path(tempfile.mkstemp(suffix="_logo.png")[1])
    logo.save(tmp, format="PNG")
    return tmp


def burn_logo_on_video_file(
    video_path: Path,
    logo_path: Path,
    output_path: Path,
    *,
    logo_on_light_path: Path | None = None,
    format_type: str | None = None,
    brief: dict | None = None,
) -> None:
    ffmpeg = require_ffmpeg()

    width, height = _video_dimensions(video_path)
    pad = max(14, int(min(width, height) * 0.025))
    # ~14% width — clearly visible in corner
    logo_w = max(56, int(width * 0.14))

    logo_png = _prepare_logo_png_for_video(
        video_path,
        logo_path,
        logo_on_light_path=logo_on_light_path,
        target_width=logo_w,
        format_type=format_type,
        brief=brief,
    )
    try:
        from PIL import Image

        with Image.open(logo_png) as logo_img:
            logo_img_w, logo_h = logo_img.size

        portrait = is_portrait_video_format(format_type, brief)
        if portrait:
            overlay_x = max(pad, width - logo_img_w - pad)
            overlay_y = max(pad, height - logo_h - pad)
        else:
            overlay_x = pad
            overlay_y = pad

        filter_complex = (
            f"[1:v]format=rgba,scale={logo_w}:-1[logo];"
            f"[0:v][logo]overlay={overlay_x}:{overlay_y}:format=auto[out]"
        )
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(logo_png),
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg logo overlay failed: {proc.stderr[-800:]}")
    finally:
        try:
            logo_png.unlink(missing_ok=True)
        except OSError:
            pass


def apply_logo_overlay_to_video_file(
    video_file_url: str,
    logo_url: str | None,
    *,
    tenant_id: str,
    logo_on_light_url: str | None = None,
    format_type: str | None = None,
    brief: dict | None = None,
    brand: dict | None = None,
) -> tuple[str | None, bool]:
    """
    Burn logo on video. Returns (url, applied).
    Resolves logo from brand/brief/env when logo_url is omitted.
    """
    from app.services.file_service import file_service
    from app.services.logo_overlay import file_url_to_local_path
    from app.services.media_content import video_suffix_and_type

    resolved_logo, resolved_on_light = resolve_video_logo_urls(
        brief=brief,
        brand=brand,
        logo_url=logo_url,
        logo_on_light_url=logo_on_light_url,
    )

    video_path = file_url_to_local_path(video_file_url)
    logo_path = logo_local_path(resolved_logo)
    if not video_path:
        logger.error("VIDEO LOGO FAILED: video not on disk %s", video_file_url[:120])
        return video_file_url, False
    if not logo_path:
        logger.error(
            "VIDEO LOGO FAILED: brand kit logo missing or not on disk. resolved=%s upload_dir=%s",
            resolved_logo,
            settings.UPLOAD_DIR,
        )
        return video_file_url, False

    if not ffmpeg_executable():
        logger.error("VIDEO LOGO FAILED: ffmpeg not installed — %s", resolved_logo[:80])
        return video_file_url, False

    logo_on_light_path = logo_local_path(resolved_on_light)
    downloaded_logo = logo_path and resolved_logo and resolved_logo.startswith("http")
    downloaded_on_light = (
        logo_on_light_path
        and resolved_on_light
        and resolved_on_light.startswith("http")
    )

    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"branded{video_path.suffix or '.mp4'}"
            burn_logo_on_video_file(
                video_path,
                logo_path,
                out,
                logo_on_light_path=logo_on_light_path,
                format_type=format_type,
                brief=brief,
            )
            content = out.read_bytes()
            suffix, content_type = video_suffix_and_type(content)
            saved = file_service.save_bytes(
                content=content,
                tenant_id=tenant_id,
                subfolder="generated",
                suffix=suffix,
                content_type=content_type,
            )
            logger.info("VIDEO LOGO OK: %s → %s", resolved_logo[:60], saved["file_url"])
            return saved["file_url"], True
    except Exception:
        logger.exception("VIDEO LOGO FAILED for %s", video_file_url)
        return video_file_url, False
    finally:
        for path, was_temp in (
            (logo_path, downloaded_logo),
            (logo_on_light_path, downloaded_on_light),
        ):
            if was_temp and path:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


def finalize_video_with_brand_logo(
    result: dict,
    *,
    brief: dict,
    format_type: str,
    tenant_id: str,
    brand: dict | None = None,
    logo_url: str | None = None,
    logo_on_light_url: str | None = None,
    spoken_script: str | None = None,
    duration_seconds: float | None = None,
) -> dict:
    """
    Mandatory post-process for every HeyGen video:
    1) Burn spoken subtitles (approved avatar script)
    2) Burn Brand Kit logo (portrait: bottom-right, landscape: top-left)
    """
    if result.get("status") != "done" or not result.get("url") or not tenant_id:
        return result

    from app.services.video_subtitles import (
        apply_spoken_subtitles_to_video_file,
        resolve_spoken_script_for_subtitles,
        sanitize_script_for_subtitles,
        subtitles_enabled,
    )

    current_url = str(result["url"])
    merged_brief = dict(brief or {})
    kb = merged_brief.get("key_benefits")
    if isinstance(kb, dict) and isinstance(kb.get("heygen_settings"), dict):
        merged_brief.setdefault("heygen_settings", kb["heygen_settings"])

    dur = float(
        duration_seconds
        or result.get("requested_duration_seconds")
        or result.get("duration_seconds")
        or 30
    )
    provider = str(result.get("provider") or "heygen")

    raw_script = (
        (spoken_script or "").strip()
        or resolve_spoken_script_for_subtitles(merged_brief, result).strip()
        or str(result.get("spoken_script") or "").strip()
        or str(result.get("avatar_script") or "").strip()
    )
    script = sanitize_script_for_subtitles(raw_script, duration=dur)
    result["subtitles_applied"] = False
    result["logo_applied"] = False

    # --- Step 1: Brand logo (HeyGen download has no Brand Kit logo) ---
    if not video_logo_overlay_enabled(merged_brief):
        result["logo_skipped"] = "brand_styled_overlay_disabled"
        logger.info("VIDEO LOGO SKIPPED: brand_styled_overlay off")
    else:
        branded_url, applied = apply_logo_overlay_to_video_file(
            current_url,
            logo_url,
            tenant_id=tenant_id,
            logo_on_light_url=logo_on_light_url,
            format_type=format_type,
            brief=merged_brief,
            brand=brand,
        )
        if branded_url:
            current_url = branded_url
        result["logo_applied"] = applied
        if not applied:
            if not ffmpeg_executable():
                result["logo_warning"] = (
                    "Logo not burned: ffmpeg is missing. In backend folder run "
                    "`pip install imageio-ffmpeg`, restart the server, then regenerate."
                )
            elif not logo_local_path(logo_url):
                result["logo_warning"] = (
                    "Logo file not found on disk. Re-upload ON DARK logo in Brand Kit, then regenerate."
                )
            else:
                result["logo_warning"] = (
                    "Logo not burned (ffmpeg error). Restart backend after installing imageio-ffmpeg."
                )

    result["url"] = current_url

    # --- Step 2: Captions on top (HeyGen preview captions are NOT in our downloaded file) ---
    if not script:
        prov = str(result.get("provider") or "").lower()
        if prov == "higgsfield" or prov.startswith("hf-"):
            result["subtitle_warning"] = (
                "No speakable script for captions — ensure the brief has ad copy or a "
                "production skeleton, then regenerate."
            )
        else:
            result["subtitle_warning"] = (
                "No spoken script — approve Avatar Script (step 8) before generating."
            )
        logger.error("VIDEO SUBTITLES SKIPPED: empty script")
    elif subtitles_enabled(merged_brief, provider=provider):
        sub_url, sub_ok = apply_spoken_subtitles_to_video_file(
            current_url,
            script,
            tenant_id=tenant_id,
            duration_seconds=dur,
            brief=merged_brief,
            format_type=format_type,
            provider=provider,
            heygen_srt_url=str(result.get("heygen_subtitle_url") or "").strip() or None,
        )
        if sub_url:
            current_url = sub_url
        result["url"] = current_url
        result["subtitles_applied"] = sub_ok
        if not sub_ok:
            if not ffmpeg_executable():
                result["subtitle_warning"] = (
                    "Captions not burned: ffmpeg is missing. Run `pip install imageio-ffmpeg` "
                    "in the backend folder, restart, then regenerate."
                )
            else:
                result["subtitle_warning"] = (
                    "Captions could not be burned onto the video. Restart backend and regenerate. "
                    "HeyGen website preview captions are not included in the download file."
                )
    else:
        result["subtitle_warning"] = "Captions disabled in HeyGen settings."

    logger.info(
        "VIDEO FINALIZE: url=%s logo=%s subs=%s",
        current_url[:80],
        result.get("logo_applied"),
        result.get("subtitles_applied"),
    )
    return result
