"""Compile timed creative briefs into local clip timelines without dropping later beats."""

from __future__ import annotations

import re

MAX_VIDEO_PROMPT_CHARS = 32_000
SHOT_HEADER = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:(?:CLIP|Scene)[ \t]*\d+\b[^\n]*|"
    r"\d+(?:\.\d+)?\s*[–—-]\s*\d+(?:\.\d+)?\s*(?:seconds?|s)\s*[—–-]\s*[^\n]+)"
)
_HEADER = SHOT_HEADER
_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:s(?:econds?)?)?\s*[–—-]\s*(\d+(?:\.\d+)?)\s*(?:s(?:econds?)?)?\b", re.I)
_GLOBAL = re.compile(r"(?im)^\s*(?:AUDIO|TEXT RULE|PRODUCT RULE|MOTION RULE|VISUAL STYLE|EDITING / TIMING|STRICT NEGATIVE|PRODUCT CINEMATOGRAPHY LOCK|FINISHING LOCK|CHARACTER CONTINUITY|On-screen copy and graphic direction|Voiceover performance and synchronisation|Camera, lighting and finishing|Music and sound mix|Generation workflow and final checks)\s*[:\n]")


def explicit_shot_windows(prompt: str, *, total: float | None = None) -> list[tuple[float, float]]:
    """Return a contiguous authored edit, or leave unstructured briefs as one clip."""
    windows = []
    for header in SHOT_HEADER.finditer(prompt):
        heading = re.sub(r"(?i)^\s*(?:#{1,6}\s*)?(?:CLIP|Scene)\s*\d+\b", "", header.group())
        timing = _RANGE.search(heading)
        if not timing:
            return []
        windows.append((float(timing.group(1)), float(timing.group(2))))
    if len(windows) < 2:
        return []
    previous = 0.0
    for a, b in windows:
        if abs(a - previous) > 0.05 or b <= a or (total is not None and b > total + 0.05):
            raise ValueError("Shot timings must be continuous, ordered, and within the requested duration.")
        previous = b
    if total is not None and abs(previous - total) > 0.05:
        raise ValueError("The shot timeline does not cover the requested video duration.")
    # Split exceptionally long shots at the provider's 15-second limit.
    pieces = []
    for a, b in windows:
        while b - a > 15:
            pieces.append((a, a + 15))
            a += 15
        pieces.append((a, b))
    return pieces


def validate_video_prompt(prompt: str) -> str:
    text = (prompt or "").strip()
    if not text:
        raise ValueError("A video prompt is required")
    if len(text) > MAX_VIDEO_PROMPT_CHARS:
        raise ValueError(
            f"Video prompt is {len(text):,} characters; maximum is "
            f"{MAX_VIDEO_PROMPT_CHARS:,}. Shorten the brief or split it into scenes."
        )
    return text


def select_complete_timeline_prompt(
    source_prompt: str,
    motion_prompt: str,
    *,
    total: float,
) -> str:
    """Prefer an authored complete timeline over a stale/rephrased motion plan.

    Both candidates are still strictly validated. This fixes cases where an LLM
    rewrite rounds a 26-second authored ending to a coarse preset while keeping
    real gaps, overlaps and incomplete timelines blocked.
    """
    candidates: list[str] = []
    for candidate in (source_prompt, motion_prompt):
        text = (candidate or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    first_error: ValueError | None = None
    for candidate in candidates:
        try:
            windows = explicit_shot_windows(candidate, total=total)
        except ValueError as exc:
            first_error = first_error or exc
            continue
        if windows:
            return candidate

    # A planner may round only the last boundary to a coarse duration preset
    # (for example 25s or 30s for a requested 26s film). If the authored shots
    # are otherwise contiguous, correct that final boundary deterministically.
    # Large differences still fail rather than stretching a short script.
    tolerance = max(2.0, float(total) * 0.20)
    rounded: list[tuple[float, str]] = []
    for candidate in candidates:
        try:
            windows = explicit_shot_windows(candidate)
        except ValueError:
            continue
        if not windows:
            continue
        authored_end = float(windows[-1][1])
        difference = abs(authored_end - float(total))
        if difference > tolerance:
            continue
        headers = list(SHOT_HEADER.finditer(candidate))
        if not headers:
            continue
        final_header = headers[-1]
        heading = final_header.group()
        timing = _RANGE.search(heading)
        if not timing:
            continue
        replacement = (
            heading[: timing.start(2)]
            + f"{float(total):g}"
            + heading[timing.end(2) :]
        )
        normalized = (
            candidate[: final_header.start()]
            + replacement
            + candidate[final_header.end() :]
        )
        # Revalidate after rewriting; never return a guessed broken timeline.
        if explicit_shot_windows(normalized, total=total):
            rounded.append((difference, normalized))
    if rounded:
        rounded.sort(key=lambda item: item[0])
        return rounded[0][1]
    if first_error:
        raise first_error
    raise ValueError("Long Seedance videos require an explicit timed multi-scene plan.")


def segment_motion_prompt(prompt: str, *, start: float, end: float, total: float) -> str:
    """Keep overlapping beats only; rebase their timing to this provider request."""
    headers = list(_HEADER.finditer(prompt))
    prefix = prompt[:headers[0].start()].strip() if headers else ""
    suffix = ""
    beats: list[str] = []
    for i, header in enumerate(headers):
        stop = headers[i + 1].start() if i + 1 < len(headers) else len(prompt)
        body = prompt[header.end():stop].strip()
        global_start = _GLOBAL.search(body)
        if global_start:
            suffix += "\n" + body[global_start.start():]
            body = body[:global_start.start()].strip()
        heading = re.sub(r"(?i)^\s*(?:#{1,6}\s*)?(?:CLIP|Scene)\s*\d+\b", "", header.group())
        timing = _RANGE.search(heading)
        a, b = (
            (float(timing.group(1)), float(timing.group(2)))
            if timing else (i * total / len(headers), (i + 1) * total / len(headers))
        )
        if b <= a or a >= end or b <= start:
            continue
        title = f"CLIP {i + 1}: " + _RANGE.sub("", heading).strip(" —-:()")
        beats.append(
            f"{title} — LOCAL {max(a, start) - start:g}–{min(b, end) - start:g} seconds:\n{body}"
        )
    if headers and not beats:
        raise ValueError(f"No scene covers {start:g}–{end:g}s. Correct the brief timeline before generating.")
    # Global duration statements are superseded by the local instruction at the beginning.
    context = re.sub(r"\b\d+(?:\.\d+)?[- ]SECOND\b", "FULL-FILM", prefix, flags=re.I)
    body = "\n\n".join(beats) if headers else prompt
    return validate_video_prompt(
        f"Generate ONLY {end - start:g} seconds for global timeline {start:g}–{end:g}s "
        f"of a {total:g}s film. All LOCAL times below start at zero. "
        "Do not replay earlier scenes or preview later scenes. "
        "Preserve the subjects, product, wardrobe and environment from the references.\n\n"
        f"{context}\n\n{body}\n\n{suffix}"
    )
