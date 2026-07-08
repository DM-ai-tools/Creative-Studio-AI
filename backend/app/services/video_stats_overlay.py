"""Burn performance dashboard screenshots into video during proof / stats beats."""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.services.brand_logo import logo_local_path
from app.services.ffmpeg_util import ffmpeg_executable, require_ffmpeg
from app.services.video_script_skeleton import (
    MIN_STAT_SLIDE_SEC,
    MAX_STAT_SLIDE_SEC,
    detect_insert_stat_segments_by_image_index,
    detect_stats_proof_window,
    pair_stats_image_segments,
    parse_spoken_lines,
    resolve_stats_image_urls,
    resolve_timed_script_for_stats_overlay,
    _timestamp_to_seconds,
)

logger = logging.getLogger(__name__)

_STATS_BG = "0x111111"
_INSERT_STAT_RE = re.compile(r"\[INSERT\s+STAT\s+IMAGE\s+(\d+)\]", re.I)


def _even(n: int) -> int:
    return max(2, n - (n % 2))


def _script_total_seconds(script: str) -> float:
    """Largest end timestamp in a timed script — its planned total length."""
    best = 0.0
    for m in re.finditer(
        r"\[(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})\]", script or ""
    ):
        end = int(m.group(3)) * 60 + int(m.group(4))
        best = max(best, float(end))
    return best


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _distinctive_stat_tokens(stats: Any) -> list[str]:
    """OCR numbers/keywords that uniquely identify when THIS dashboard is spoken."""
    raw_vals = [
        getattr(stats, "headline_stat", None),
        getattr(stats, "roas", None),
        getattr(stats, "purchases_sales", None),
        getattr(stats, "cost", None),
        getattr(stats, "lead_forms", None),
        getattr(stats, "conversion_value", None),
        getattr(stats, "conv_value_per_cost", None),
    ]
    tokens: list[str] = []
    for val in raw_vals:
        if not val:
            continue
        s = str(val).lower()
        for m in re.finditer(r"\d+(?:\.\d+)?", s):
            tok = m.group(0)
            if len(tok) >= 2 or "%" in s or "$" in s:
                tokens.append(tok)
        if "million" in s:
            tokens.append("million")
        if "roas" in s:
            tokens.append("roas")
    # De-dupe, keep order
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _proof_phrases_by_image(
    script: str,
    *,
    brief: dict | None = None,
) -> dict[int, str]:
    """Spoken proof line per stat image — from INSERT markers or OCR-matched voice beats."""
    out: dict[int, str] = {}

    for m in _INSERT_STAT_RE.finditer(script or ""):
        idx = int(m.group(1)) - 1
        tail = script[m.end() :]
        line_end = tail.find("\n")
        tail = tail[:line_end] if line_end >= 0 else tail
        tail = re.sub(r"\s+", " ", tail).strip()
        if tail and 0 <= idx:
            out[idx] = tail

    if brief:
        from app.services.stats_image_service import (
            build_spoken_proof_line_for_image,
            resolve_performance_stats_per_image_from_brief,
            spoken_line_matches_stats,
        )

        per_image = resolve_performance_stats_per_image_from_brief(brief)
        brand = str(brief.get("brand_name") or brief.get("product_name") or "").strip()
        script_dur = max(30, int(_script_total_seconds(script) or 90))
        lines = parse_spoken_lines(script, duration=script_dur)
        used_lines: set[int] = set()
        for i, stats in enumerate(per_image):
            if i in out:
                continue
            for line_idx, (_start, _end, say) in enumerate(lines):
                if line_idx in used_lines:
                    continue
                line_sec = float(_timestamp_to_seconds(_start))
                if spoken_line_matches_stats(
                    say, stats, line_start_sec=line_sec, script_duration=float(script_dur)
                ):
                    out[i] = re.sub(r"\[INSERT\b[^\]]*\]\s*", "", say, flags=re.I).strip()
                    used_lines.add(line_idx)
                    break
            if i not in out:
                proof = build_spoken_proof_line_for_image(stats, brand_name=brand)
                if proof:
                    out[i] = proof
    return out


def _planned_beat_start_sec(script: str, image_index: int, *, duration: int) -> float | None:
    """Script timestamp where [INSERT STAT IMAGE N] is spoken."""
    for start, _end, say in parse_spoken_lines(script, duration=duration):
        if re.search(rf"\[INSERT\s+STAT\s+IMAGE\s+{image_index + 1}\b", say, re.I):
            return float(_timestamp_to_seconds(start))
    return None


def _match_phrase_window_in_srt(
    events: list[tuple[float, float, str, bool]],
    phrase: str,
    *,
    duration: float,
    required_tokens: list[str] | None = None,
    min_start: float = 0.0,
    search_from: float | None = None,
    search_to: float | None = None,
) -> tuple[float, float] | None:
    """Find when a spoken phrase occurs in HeyGen's SRT (audio-accurate)."""
    phrase_words = _tokenize(phrase)
    if not phrase_words or not events:
        return None

    window_lo = max(min_start, search_from if search_from is not None else 0.0)
    window_hi = search_to if search_to is not None else float(duration)
    # Default search window starts after hook — avoids matching opening line in SRT.
    if search_from is None:
        window_lo = max(window_lo, _hook_zone_end(duration))

    word_times: list[tuple[str, float, float]] = []
    for t0, t1, text, _ in events:
        if t1 < window_lo or t0 > window_hi:
            continue
        ws = _tokenize(text)
        if not ws:
            continue
        step = max(0.05, (t1 - t0) / len(ws))
        for k, w in enumerate(ws):
            wt0 = t0 + k * step
            if wt0 < window_lo or wt0 > window_hi:
                continue
            word_times.append((w, wt0, t0 + (k + 1) * step))

    if not word_times:
        return None

    req = [t.lower() for t in (required_tokens or []) if t and len(t) >= 2]
    win_len = max(4, len(phrase_words))
    best_score = 0
    best_span: tuple[float, float] | None = None
    n = len(word_times)
    for i in range(n):
        if word_times[i][1] < window_lo:
            continue
        j = min(n, i + win_len + 4)
        window = word_times[i:j]
        window_text = " ".join(wt[0] for wt in window)
        score = sum(1 for wt in window if wt[0] in phrase_words)
        if req:
            matched_req = sum(1 for t in req if t in window_text)
            if matched_req < min(2, len(req)):
                continue
            score += matched_req * 3
        if score > best_score:
            best_score = score
            best_span = (window[0][1], window[-1][2])

    threshold = max(5, win_len // 2)
    if req:
        threshold = max(threshold, 6)
    if best_span and best_score >= threshold:
        s, e = best_span
        s = max(window_lo, s)
        e = min(float(duration), window_hi, max(e, s + MIN_STAT_SLIDE_SEC))
        if e - s > MAX_STAT_SLIDE_SEC:
            e = min(float(duration), s + MAX_STAT_SLIDE_SEC)
        return s, e
    return None


def _segments_from_voice_proof_beats(
    script: str,
    stats_count: int,
    *,
    duration: int,
    brief: dict | None = None,
) -> list[tuple[float, float] | None]:
    """Map each image index to the voice beat that cites its OCR figures."""
    from app.services.stats_image_service import (
        resolve_performance_stats_per_image_from_brief,
        spoken_line_matches_stats,
    )
    from app.services.video_script_skeleton import _extend_stat_segment

    per_image = resolve_performance_stats_per_image_from_brief(brief) if brief else []
    lines = parse_spoken_lines(script, duration=duration)
    if not lines:
        return [None] * stats_count

    segments: list[tuple[float, float] | None] = [None] * stats_count
    used_line_idx: set[int] = set()

    # Pass 1: exact [INSERT STAT IMAGE N] markers
    for line_idx, (start, end, say) in enumerate(lines):
        m = re.search(r"\[INSERT\s+STAT\s+IMAGE\s+(\d+)\]", say, re.I)
        if not m:
            continue
        i = int(m.group(1)) - 1
        if 0 <= i < stats_count and segments[i] is None:
            s = float(_timestamp_to_seconds(start))
            e = float(min(_timestamp_to_seconds(end), duration))
            segments[i] = _extend_stat_segment(s, e, float(duration))
            used_line_idx.add(line_idx)

    # Pass 2: OCR figure match — one line per image, in script order
    for i in range(stats_count):
        if segments[i] is not None:
            continue
        stats = per_image[i] if i < len(per_image) else None
        if not stats:
            continue
        for line_idx, (start, end, say) in enumerate(lines):
            if line_idx in used_line_idx:
                continue
            line_sec = float(_timestamp_to_seconds(start))
            if spoken_line_matches_stats(
                say, stats, line_start_sec=line_sec, script_duration=float(duration)
            ):
                s = float(_timestamp_to_seconds(start))
                e = float(min(_timestamp_to_seconds(end), duration))
                segments[i] = _extend_stat_segment(s, e, float(duration))
                used_line_idx.add(line_idx)
                break

    return segments


def _hook_zone_end(dur: float) -> float:
    """Never show stat cards during the opening hook."""
    return min(45.0, max(10.0, float(dur) * 0.20))


def _enforce_segment_floors(
    segments: list[tuple[float, float]],
    script: str,
    *,
    calc_dur: int,
    ratio: float,
    dur: float,
) -> list[tuple[float, float]]:
    """Push overlay windows out of the hook zone and onto planned proof beats."""
    hook_end = _hook_zone_end(dur)
    out: list[tuple[float, float]] = []
    for i, (s, e) in enumerate(segments):
        planned = _planned_beat_start_sec(script, i, duration=calc_dur)
        floor = hook_end
        if planned is not None:
            floor = max(hook_end, planned * ratio - 1.0)
        if s < floor:
            s = floor
            e = max(e, s + MIN_STAT_SLIDE_SEC)
        e = min(e, dur)
        out.append((max(0.0, s), max(0.0, e)))
    return _trim_overlaps_preserve_index(out, dur)


def _trim_overlaps_preserve_index(
    segments: list[tuple[float, float]],
    duration: float,
) -> list[tuple[float, float]]:
    """Fix overlaps without reordering — image N always stays image N."""
    if not segments:
        return segments
    out = list(segments)
    for i in range(1, len(out)):
        prev_s, prev_e = out[i - 1]
        s, e = out[i]
        if s < prev_e - 0.05:
            s = prev_e + 0.15
            e = max(e, s + MIN_STAT_SLIDE_SEC)
            e = min(e, float(duration))
            out[i] = (s, e)
    return out


def _video_dimensions(video_path: Path) -> tuple[int, int]:
    """Probe the actual video dimensions; default to 1920×1080 landscape."""
    from app.services.ffmpeg_util import ffprobe_executable

    ffprobe = ffprobe_executable()
    if not ffprobe:
        return 1920, 1080

    proc = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and "x" in proc.stdout:
        try:
            w, h = proc.stdout.strip().split("x", 1)
            return max(1, int(w)), max(1, int(h))
        except ValueError:
            pass
    return 1920, 1080


def burn_stats_images_on_video_file(
    video_path: Path,
    stats_paths: list[Path],
    output_path: Path,
    *,
    segments: list[tuple[float, float]],
) -> None:
    """Overlay stats dashboards as a side/top card — presenter stays visible."""
    if not stats_paths:
        raise ValueError("No stats images to overlay")
    if len(segments) < len(stats_paths):
        raise ValueError("Not enough time segments for stats images")
    ffmpeg = require_ffmpeg()
    width, height = _video_dimensions(video_path)
    width, height = _even(width), _even(height)

    portrait = height > width
    if portrait:
        # Top strip — avatar reads below the card
        card_w = _even(int(width * 0.90))
        card_h = _even(int(height * 0.26))
        x_expr = "(W-w)/2"
        y_expr = "H*0.05"
    else:
        # Right-side panel — presenter stays on the left
        card_w = _even(int(width * 0.40))
        card_h = _even(int(height * 0.50))
        x_expr = "W-w-20"
        y_expr = "(H-h)/2"

    parts: list[str] = []
    for i in range(len(stats_paths)):
        parts.append(
            f"[{i + 1}:v]scale={card_w}:{card_h}:force_original_aspect_ratio=decrease,"
            f"setsar=1[stats{i}]"
        )

    prev = "[0:v]"
    for i in range(len(stats_paths)):
        seg_start = max(0.0, float(segments[i][0]))
        seg_end = max(seg_start + 0.5, float(segments[i][1]))
        out_label = "[out]" if i == len(stats_paths) - 1 else f"[v{i}]"
        parts.append(
            f"{prev}[stats{i}]overlay={x_expr}:{y_expr}:"
            f"enable='between(t,{seg_start:.2f},{seg_end:.2f})'{out_label}"
        )
        prev = out_label

    filter_complex = ";".join(parts)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
    ]
    for stats_path in stats_paths:
        cmd.extend(["-loop", "1", "-i", str(stats_path)])
    cmd.extend(
        [
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
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg stats overlay failed: {proc.stderr[-1200:]}")


def burn_stats_image_on_video_file(
    video_path: Path,
    stats_path: Path,
    output_path: Path,
    *,
    start_sec: float,
    end_sec: float,
) -> None:
    """Single-image overlay (legacy helper)."""
    burn_stats_images_on_video_file(
        video_path,
        [stats_path],
        output_path,
        segments=[(start_sec, end_sec)],
    )


def apply_stats_overlay_to_video_file(
    video_file_url: str,
    *,
    brief: dict | None,
    spoken_script: str,
    duration_seconds: float,
    tenant_id: str,
    subtitle_srt: str | None = None,
) -> tuple[str | None, bool, dict]:
    """
    Overlay stats dashboard(s) during proof beat. Returns (url, applied, meta).
    """
    from app.services.file_service import file_service
    from app.services.logo_overlay import file_url_to_local_path
    from app.services.media_content import video_suffix_and_type
    from app.services.stats_image_service import resolve_performance_stats_per_image_from_brief

    stats_urls = resolve_stats_image_urls(brief)
    if not stats_urls:
        return video_file_url, False, {}

    video_path = file_url_to_local_path(video_file_url)
    stats_paths: list[Path] = []
    downloaded: list[Path] = []
    for url in stats_urls:
        path = logo_local_path(url)
        if path and path.is_file():
            stats_paths.append(path)
            if url.startswith("http"):
                downloaded.append(path)

    if not video_path or not stats_paths:
        logger.warning(
            "STATS OVERLAY SKIPPED: video=%s stats=%s/%s urls=%s",
            bool(video_path),
            len(stats_paths),
            len(stats_urls),
            stats_urls[:2],
        )
        return video_file_url, False, {"stats_overlay_warning": "Stats image file not found"}

    if not ffmpeg_executable():
        return video_file_url, False, {
            "stats_overlay_warning": "ffmpeg missing — stats image not burned into video"
        }

    dur = float(max(5, round(duration_seconds)))
    timed_script = resolve_timed_script_for_stats_overlay(brief, {"avatar_script": spoken_script})
    broll_script = ""
    if brief:
        from app.services.video_script_skeleton import _heygen_scene_broll_raw

        broll_script = _heygen_scene_broll_raw(brief)
    script = timed_script or (spoken_script or "").strip()

    plan_dur = _script_total_seconds(script)
    calc_dur = int(round(plan_dur)) if plan_dur >= 5 else int(dur)

    start_sec, end_sec = detect_stats_proof_window(
        script, duration=calc_dur, broll_script=broll_script
    )

    n = len(stats_paths)
    ratio = 1.0
    if calc_dur > 0 and abs(calc_dur - dur) > 0.5:
        ratio = dur / float(calc_dur)

    # Build per-image-index segments (image 0 → card 0, etc.) — never reorder by time.
    indexed = detect_insert_stat_segments_by_image_index(script, n, duration=calc_dur)
    voice_indexed = _segments_from_voice_proof_beats(
        script, n, duration=calc_dur, brief=brief
    )
    segments: list[tuple[float, float]] = []
    for i in range(n):
        seg = indexed[i] or voice_indexed[i]
        if seg is None:
            fallback = pair_stats_image_segments(
                n, script, duration=calc_dur, broll_script=broll_script
            )
            if i < len(fallback):
                seg = fallback[i]
            else:
                seg = (
                    max(start_sec, _hook_zone_end(dur)),
                    max(end_sec, _hook_zone_end(dur) + MIN_STAT_SLIDE_SEC),
                )
        s, e = seg
        if ratio != 1.0:
            s, e = s * ratio, e * ratio
        segments.append((s, e))

    per_image = resolve_performance_stats_per_image_from_brief(brief)
    phrases = _proof_phrases_by_image(script, brief=brief)

    srt_matched = 0
    if subtitle_srt:
        from app.services.video_subtitles import parse_srt_to_events

        events = parse_srt_to_events(subtitle_srt, max_events=None)
        if events and phrases:
            min_start = _hook_zone_end(dur)
            for i in range(n):
                phrase = phrases.get(i, "")
                stats = per_image[i] if i < len(per_image) else None
                req_tokens = _distinctive_stat_tokens(stats) if stats else []
                planned = _planned_beat_start_sec(script, i, duration=calc_dur)
                search_from = None
                search_to = None
                if planned is not None:
                    anchor = planned * ratio
                    search_from = max(0.0, anchor - 4.0)
                    search_to = min(dur, anchor + 18.0)
                win = _match_phrase_window_in_srt(
                    events,
                    phrase,
                    duration=dur,
                    required_tokens=req_tokens,
                    min_start=min_start,
                    search_from=search_from,
                    search_to=search_to,
                )
                if win:
                    segments[i] = win
                    srt_matched += 1
                    min_start = win[1] + 0.1

    segments = _enforce_segment_floors(
        [(max(0.0, min(s, dur)), max(0.0, min(e, dur))) for s, e in segments],
        script,
        calc_dur=calc_dur,
        ratio=ratio,
        dur=dur,
    )
    if segments:
        start_sec, end_sec = segments[0][0], segments[-1][1]

    logger.info(
        "STATS OVERLAY timing: timed=%s plan=%ss actual=%ss ratio=%.3f srt_matched=%s/%s segments=%s phrases=%s",
        bool(timed_script),
        calc_dur,
        dur,
        ratio,
        srt_matched,
        len(stats_paths),
        [(round(a, 1), round(b, 1)) for a, b in segments],
        list(phrases.keys()),
    )

    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"stats_overlay{video_path.suffix or '.mp4'}"
            burn_stats_images_on_video_file(
                video_path,
                stats_paths,
                out,
                segments=segments,
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
            logger.info(
                "STATS OVERLAY OK: segments=%s images=%s on %s",
                [(round(a, 1), round(b, 1)) for a, b in segments],
                len(stats_paths),
                saved["file_url"][:80],
            )
            return (
                saved["file_url"],
                True,
                {
                    "stats_overlay_applied": True,
                    "stats_overlay_start_sec": start_sec,
                    "stats_overlay_end_sec": end_sec,
                    "stats_overlay_segments": segments,
                    "stats_overlay_image_count": len(stats_paths),
                    "stats_overlay_srt_matched": srt_matched,
                },
            )
    except Exception:
        logger.exception("STATS OVERLAY FAILED for %s", video_file_url[:80])
        return video_file_url, False, {
            "stats_overlay_warning": "Could not burn stats dashboard into video"
        }
    finally:
        for path in downloaded:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
