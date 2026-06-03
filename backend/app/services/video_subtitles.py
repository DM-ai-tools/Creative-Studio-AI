"""Burn spoken-word subtitles onto videos (ffmpeg — Windows-safe paths)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.logo_overlay import file_url_to_local_path
from app.services.ffmpeg_util import (
    drawtext_font_opts,
    ffmpeg_executable,
    probe_video_duration,
    require_ffmpeg,
)
from app.services.video_script_skeleton import (
    extract_heygen_spoken_script,
    parse_spoken_lines,
)

logger = logging.getLogger(__name__)

_MAX_WORDS_PER_LINE = 6
_SPEECH_START_PAD_SEC = 0.45
_SPEECH_END_PAD_SEC = 0.35
_MIN_WORDS_PER_SEC = 2.0
_MAX_WORDS_PER_SEC = 3.2
_SRT_BLOCK = re.compile(
    r"(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n((?:.+\n?)+?)(?=\n\d+\s*\n|\Z)",
    re.MULTILINE,
)
_PROMPT_MARKERS = re.compile(
    r"(PRODUCTION SCRIPT|SPOKEN SCRIPT|SCRIPT-TO-VIDEO|mandatory|Avatar Speaks:|"
    r"Scene Direction:|VISUAL AUTO|B-ROLL PEOPLE|CRITICAL —)",
    re.I,
)


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


def subtitles_enabled(brief: dict | None, *, provider: str | None = None) -> bool:
    """Burn captions for HeyGen and Higgsfield/Runway (ffmpeg), not in the AI render."""
    prov = (provider or "").strip().lower()
    if prov and prov not in ("heygen", "heygen-video-agent", "higgsfield", "runway"):
        if not prov.startswith("hf-") and "runway" not in prov:
            return False
    heygen = _heygen_settings(brief)
    if heygen.get("burn_in_captions") is False:
        return False
    return True


def sanitize_script_for_subtitles(text: str, *, duration: float = 30) -> str:
    """Keep only speakable dialogue — not HeyGen prompts or production skeleton headers."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return ""

    if _PROMPT_MARKERS.search(raw) or len(raw) > 1200:
        extracted = extract_heygen_spoken_script(raw, target_seconds=int(duration))
        if extracted and len(extracted) > 20 and not _PROMPT_MARKERS.search(extracted[:200]):
            raw = extracted

    raw = re.sub(r"\[\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\]\s*", " ", raw)
    raw = re.sub(r"\s*[—–]\s*", " ", raw)
    raw = re.sub(
        r"\b(Open with a direct hook|Establish credibility|talking points|scriptwriter)\b[^.]*\.?",
        "",
        raw,
        flags=re.I,
    )
    return " ".join(raw.split()).strip()


def resolve_spoken_script_for_subtitles(
    brief: dict | None,
    result: dict | None,
    *,
    copy: dict | None = None,
) -> str:
    """Avatar script → production skeleton → Higgsfield/Runway voiceover script → ad copy."""
    brief = brief or {}
    result = result or {}
    kb = brief.get("key_benefits") if isinstance(brief.get("key_benefits"), dict) else {}
    dur = float(
        result.get("requested_duration_seconds")
        or result.get("duration_seconds")
        or 30
    )

    vo = result.get("voiceover")
    if isinstance(vo, dict) and vo.get("script"):
        cleaned = sanitize_script_for_subtitles(str(vo["script"]), duration=dur)
        if cleaned:
            return cleaned

    if result.get("spoken_script"):
        cleaned = sanitize_script_for_subtitles(str(result["spoken_script"]), duration=dur)
        if cleaned:
            return cleaned

    for src in (
        brief.get("avatar_script"),
        kb.get("avatar_script"),
        result.get("avatar_script"),
        kb.get("pdf_script_text"),
        brief.get("pdf_script_text"),
    ):
        if src and str(src).strip():
            cleaned = sanitize_script_for_subtitles(str(src), duration=dur)
            if cleaned:
                return cleaned

    skeleton = (
        brief.get("video_script_skeleton")
        or kb.get("video_script_skeleton")
        or ""
    )
    if skeleton:
        cleaned = sanitize_script_for_subtitles(str(skeleton), duration=dur)
        if cleaned:
            return cleaned

    if copy or brief:
        from app.services.media.voiceover import build_voiceover_script

        merged_copy = dict(copy or {})
        for key in ("hook", "headline", "body_copy", "cta", "offer"):
            if not merged_copy.get(key) and brief.get(key):
                merged_copy[key] = brief.get(key)
        vo_script = build_voiceover_script(copy=merged_copy, brief=brief)
        cleaned = sanitize_script_for_subtitles(vo_script, duration=dur)
        if cleaned:
            return cleaned

    return ""


def _mmss_to_seconds(ts: str) -> float:
    parts = ts.strip().split(":")
    if len(parts) != 2:
        return 0.0
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return 0.0


def _seconds_to_ass(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _hex_to_ass_color(hex_color: str, *, default: str = "FFFFFF") -> str:
    raw = (hex_color or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    if len(raw) != 6:
        raw = default
    try:
        r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError:
        r, g, b = 255, 255, 255
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _video_dimensions(video_path: Path) -> tuple[int, int]:
    from app.services.video_logo_overlay import _video_dimensions

    return _video_dimensions(video_path)


def _chunk_words(text: str, max_words: int = _MAX_WORDS_PER_LINE) -> list[str]:
    words = re.sub(r"\s+", " ", (text or "").strip()).split()
    if not words:
        return []
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def _srt_timestamp_to_seconds(ts: str) -> float:
    h, m, rest = ts.strip().split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt_to_events(srt_text: str) -> list[tuple[float, float, str, bool]]:
    """Parse HeyGen / standard SRT into burn events."""
    events: list[tuple[float, float, str, bool]] = []
    for m in _SRT_BLOCK.finditer(srt_text or ""):
        t0 = _srt_timestamp_to_seconds(m.group(2))
        t1 = _srt_timestamp_to_seconds(m.group(3))
        text = " ".join(m.group(4).strip().splitlines()).strip()
        text = re.sub(r"\s+", " ", text)
        if not text or t1 <= t0:
            continue
        events.append((t0, t1, text, False))
    return events[:40]


def _download_text_url(url: str) -> str | None:
    if not url or not str(url).startswith(("http://", "https://")):
        return None
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception:
        logger.exception("Failed to download subtitle file from %s", url[:80])
        return None


def _script_has_timestamps(text: str) -> bool:
    return bool(re.search(r"\[\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\]", text or ""))


def _build_word_aligned_events(
    spoken_script: str,
    duration: float,
    *,
    brief: dict | None = None,
) -> list[tuple[float, float, str, bool]]:
    """
    Spread words across the real video duration so captions track speech pace.
    Uses the approved script (what HeyGen was asked to say).
    """
    words = sanitize_script_for_subtitles(spoken_script, duration=duration).split()
    if not words:
        return []

    dur = max(5.0, float(duration))
    speech_start = _SPEECH_START_PAD_SEC
    speech_end = max(speech_start + 2.0, dur - _SPEECH_END_PAD_SEC)
    speech_span = speech_end - speech_start
    total = len(words)

    events: list[tuple[float, float, str, bool]] = []
    idx = 0
    while idx < total:
        take = min(_MAX_WORDS_PER_LINE, total - idx)
        chunk_words = words[idx : idx + take]
        wcount = len(chunk_words)
        t0 = speech_start + (idx / total) * speech_span
        t1 = speech_start + ((idx + wcount) / total) * speech_span
        t1 = max(t1, t0 + 0.85)
        text = " ".join(chunk_words)
        hi = idx == 0 or _line_is_highlight(text, brief=brief)
        events.append((t0, min(t1, speech_end), text, hi))
        idx += take

    if events:
        last = events[-1]
        events[-1] = (last[0], speech_end, last[2], last[3])
    return events[:32]


def _build_timed_events_from_markers(
    spoken_script: str,
    duration: float,
    *,
    brief: dict | None = None,
) -> list[tuple[float, float, str, bool]]:
    """Use [MM:SS - MM:SS] lines from skeleton, scaled to actual video length."""
    lines = parse_spoken_lines(spoken_script, duration=max(5, int(duration)))
    if not lines:
        return []

    raw_ends = [_mmss_to_seconds(end) for _, end, _ in lines]
    script_end = max(raw_ends) if raw_ends else float(duration)
    scale = float(duration) / max(script_end, 1.0)

    events: list[tuple[float, float, str, bool]] = []
    for start_ts, end_ts, say in lines:
        say = " ".join(say.split())
        if not say:
            continue
        t0 = _mmss_to_seconds(start_ts) * scale
        t1 = _mmss_to_seconds(end_ts) * scale
        if t1 <= t0:
            t1 = t0 + max(1.5, (duration / max(len(lines), 1)) * 0.8)
        chunks = _chunk_words(say)
        n = max(len(chunks), 1)
        for i, chunk in enumerate(chunks):
            if not chunk:
                continue
            frac0 = i / n
            frac1 = (i + 1) / n
            c0 = t0 + (t1 - t0) * frac0
            c1 = t0 + (t1 - t0) * frac1
            hi = i == 0 or _line_is_highlight(chunk, brief=brief)
            events.append((c0, max(c1, c0 + 0.8), chunk, hi))
    return events[:32]


def _build_timed_events(
    spoken_script: str,
    duration: float,
    *,
    brief: dict | None = None,
    heygen_srt_url: str | None = None,
) -> list[tuple[float, float, str, bool]]:
    """(start_sec, end_sec, text, highlight) — prefer HeyGen SRT, else audio-aligned script."""
    if heygen_srt_url:
        srt_body = _download_text_url(heygen_srt_url)
        if srt_body:
            srt_events = parse_srt_to_events(srt_body)
            if srt_events:
                logger.info("SUBTITLES: using HeyGen SRT (%s cues)", len(srt_events))
                return srt_events

    script = sanitize_script_for_subtitles(spoken_script, duration=duration)
    if _script_has_timestamps(spoken_script):
        marker_events = _build_timed_events_from_markers(
            spoken_script, duration, brief=brief
        )
        if marker_events:
            logger.info("SUBTITLES: scaled skeleton timestamps (%s cues)", len(marker_events))
            return marker_events

    aligned = _build_word_aligned_events(script, duration, brief=brief)
    logger.info("SUBTITLES: word-aligned to %.1fs video (%s cues)", duration, len(aligned))
    return aligned


def _line_is_highlight(text: str, *, brief: dict | None) -> bool:
    lower = text.lower()
    kb = brief.get("key_benefits") if brief and isinstance(brief.get("key_benefits"), dict) else {}
    for val in (brief.get("product_name") if brief else None, kb.get("offer"), brief.get("cta") if brief else None):
        if val and len(str(val)) >= 4 and str(val).lower() in lower:
            return True
    return bool(re.search(r"\b(free|save|offer|book|call|shop|learn more|google|leads)\b", lower))


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _escape_drawtext(text: str) -> str:
    cleaned = (
        text.replace("\\", " ")
        .replace("'", "")
        .replace(":", " ")
        .replace("%", " ")
        .replace(",", " ")
        .replace(";", " ")
    )
    return cleaned.strip()[:120]


def build_ass_subtitles(
    events: list[tuple[float, float, str, bool]],
    *,
    width: int,
    height: int,
    brief: dict | None = None,
) -> str:
    brand = brief or {}
    accent = _hex_to_ass_color(str(brand.get("secondary_color") or "#A3D16B"))
    margin_v = max(48, int(height * 0.08))
    font_size = max(56, int(height * 0.045))
    highlight_size = font_size + 10

    header = f"""[Script Info]
Title: CreativeStudio
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,3,5,2,2,48,48,{margin_v},1
Style: Highlight,Arial,{highlight_size},{accent},&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,3,6,2,2,48,48,{margin_v - 4},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows: list[str] = []
    for t0, t1, text, hi in events:
        style = "Highlight" if hi else "Default"
        rows.append(
            f"Dialogue: 0,{_seconds_to_ass(t0)},{_seconds_to_ass(t1)},"
            f"{style},,0,0,0,,{_escape_ass_text(text)}"
        )
    return header + "\n".join(rows) + "\n"


def _burn_with_cwd_ass(video_in: Path, ass_path: Path, output_path: Path) -> bool:
    """Burn ASS using relative path + cwd — avoids Windows drive-letter colon bugs."""
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        return False
    work_dir = video_in.parent
    rel_video = video_in.name
    rel_ass = ass_path.name
    if output_path.exists():
        output_path.unlink()
    for vf in (f"subtitles={rel_ass}:charenc=UTF-8", f"ass={rel_ass}"):
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            rel_video,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            output_path.name,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(work_dir))
        if proc.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 1000:
            logger.info("Subtitle cwd-ass OK (%s)", vf[:30])
            return True
        logger.error(
            "Subtitle cwd-ass failed (%s) rc=%s: %s",
            vf[:30],
            proc.returncode,
            (proc.stderr or "")[-800:],
        )
    return False


def _burn_with_drawtext(
    video_in: Path,
    events: list[tuple[float, float, str, bool]],
    output_path: Path,
    *,
    height: int,
) -> bool:
    """Fallback burn — keep filter chain short (Windows command-line limits)."""
    ffmpeg = ffmpeg_executable()
    if not ffmpeg or not events:
        return False
    font = drawtext_font_opts()
    y_pos = max(100, int(height * 0.76))
    base_size = max(48, int(height * 0.042))
    filters: list[str] = []
    for t0, t1, text, hi in events[:8]:
        esc = _escape_drawtext(text)
        if not esc:
            continue
        size = base_size + 10 if hi else base_size
        color = "0xFFE566" if hi else "white"
        filters.append(
            f"drawtext={font}:text='{esc}':fontsize={size}:fontcolor={color}:"
            f"borderw=5:bordercolor=black@1.0:"
            f"box=1:boxcolor=black@0.72:boxborderw=12:"
            f"x=(w-text_w)/2:y={y_pos}:"
            f"enable='between(t\\,{t0:.2f}\\,{t1:.2f})'"
        )
    if not filters:
        return False
    if output_path.exists():
        output_path.unlink()
    vf = ",".join(filters)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_in),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("drawtext burn failed rc=%s: %s", proc.returncode, (proc.stderr or "")[-500:])
        return False
    return output_path.is_file() and output_path.stat().st_size > 1000


def _ensure_local_video(video_file_url: str, *, tenant_id: str) -> Path | None:
    """Resolve /files/... path or download remote HeyGen URL into uploads."""
    local = file_url_to_local_path(video_file_url)
    if local and local.is_file():
        return local

    if not video_file_url.startswith(("http://", "https://")):
        return None

    try:
        with httpx.Client(timeout=300.0, follow_redirects=True) as client:
            resp = client.get(video_file_url)
            resp.raise_for_status()
            content = resp.content
    except Exception:
        logger.exception("Failed to download remote video for subtitles: %s", video_file_url[:80])
        return None

    if len(content) < 1000:
        return None
    if len(content) > settings.MAX_UPLOAD_SIZE:
        logger.error("Remote video too large for subtitle burn (%s bytes)", len(content))
        return None

    from app.services.file_service import file_service
    from app.services.media_content import video_suffix_and_type

    suffix, content_type = video_suffix_and_type(content)
    saved = file_service.save_bytes(
        content=content,
        tenant_id=tenant_id,
        subfolder="generated",
        suffix=suffix,
        content_type=content_type,
    )
    return file_url_to_local_path(saved["file_url"])


def apply_spoken_subtitles_to_video_file(
    video_file_url: str,
    spoken_script: str,
    *,
    tenant_id: str,
    duration_seconds: float = 30,
    brief: dict | None = None,
    format_type: str | None = None,
    provider: str | None = None,
    heygen_srt_url: str | None = None,
) -> tuple[str | None, bool]:
    dur = max(5.0, float(duration_seconds or 30))
    script = sanitize_script_for_subtitles(spoken_script or "", duration=dur)
    if not script:
        script = resolve_spoken_script_for_subtitles(brief, None)
    if not script:
        logger.error("SUBTITLES SKIPPED: no speakable script text")
        return video_file_url, False
    if not subtitles_enabled(brief, provider=provider):
        logger.info("SUBTITLES SKIPPED: burn_in_captions disabled")
        return video_file_url, False
    if not ffmpeg_executable():
        logger.error("SUBTITLES SKIPPED: ffmpeg not installed (pip install imageio-ffmpeg)")
        return video_file_url, False

    from app.services.file_service import file_service
    from app.services.media_content import video_suffix_and_type

    video_path = _ensure_local_video(video_file_url, tenant_id=tenant_id)
    if not video_path or not video_path.is_file():
        logger.error("SUBTITLES SKIPPED: cannot access video file url=%s", video_file_url[:120])
        return video_file_url, False

    probed = probe_video_duration(video_path)
    if probed and probed > 1.0:
        if abs(probed - dur) > 1.5:
            logger.info(
                "SUBTITLES: sync duration %.1fs (brief asked %.1fs) — using actual video length",
                probed,
                dur,
            )
        dur = probed

    logger.info("SUBTITLES: burning %d chars, dur=%.1fs, file=%s", len(script), dur, video_path.name)
    events = _build_timed_events(
        script,
        dur,
        brief=brief,
        heygen_srt_url=heygen_srt_url,
    )
    if not events:
        logger.error("SUBTITLES SKIPPED: no timed events from script=%r", script[:80])
        return video_file_url, False
    logger.info("SUBTITLES: %d caption lines", len(events))

    width, height = _video_dimensions(video_path)

    try:
        with tempfile.TemporaryDirectory(prefix="cs_sub_") as tmp:
            tmp_path = Path(tmp)
            work_in = tmp_path / "input.mp4"
            shutil.copy2(video_path, work_in)
            ass_file = tmp_path / "subs.ass"
            ass_file.write_text(
                build_ass_subtitles(events, width=width, height=height, brief=brief),
                encoding="utf-8-sig",
            )
            out = tmp_path / "out.mp4"

            # ASS first — reliable on Windows; drawtext chain often hits CLI/filter limits.
            ok = _burn_with_cwd_ass(work_in, ass_file, out)
            if not ok:
                ok = _burn_with_drawtext(work_in, events, out, height=height)

            if not ok:
                logger.error(
                    "SUBTITLES FAILED: all burn methods failed (lines=%s, ass=%s bytes)",
                    len(events),
                    ass_file.stat().st_size if ass_file.is_file() else 0,
                )
                return video_file_url, False

            content = out.read_bytes()
            suffix, content_type = video_suffix_and_type(content)
            saved = file_service.save_bytes(
                content=content,
                tenant_id=tenant_id,
                subfolder="generated",
                suffix=suffix,
                content_type=content_type,
            )
            logger.info(
                "SUBTITLES OK: %d lines → %s (%s bytes)",
                len(events),
                saved["file_url"],
                len(content),
            )
            return saved["file_url"], True
    except Exception:
        logger.exception("Subtitle burn failed")
        return video_file_url, False
