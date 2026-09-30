"""Compile timed creative briefs into local clip timelines without dropping later beats."""

from __future__ import annotations

import re

MAX_VIDEO_PROMPT_CHARS = 32_000
SHOT_HEADER = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:(?:(?:CLIP|Scene)[ \t]*\d+|S\d+[A-Za-z]?)[^\n]*|"
    r"\d+(?:\.\d+)?\s*[–—-]\s*\d+(?:\.\d+)?\s*(?:seconds?|s)\s*[—–-]\s*[^\n]+)"
)
_HEADER = SHOT_HEADER
_TIME_VALUE = r"(?:\d{1,2}:\d{2}(?:\.\d+)?|\d+(?:\.\d+)?)"
_RANGE = re.compile(
    rf"({_TIME_VALUE})\s*(?:s(?:econds?)?)?\s*[–—-]\s*"
    rf"({_TIME_VALUE})\s*(?:s(?:econds?)?)?\b",
    re.I,
)
_SESSION_HEADER = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:STEP\s+\d+\s*[—–-]\s*)?"
    r"SESSION\s+([A-Za-z0-9]+)\s*\|\s*"
    rf"({_TIME_VALUE})\s*[–—-]\s*"
    rf"({_TIME_VALUE})[^\n]*"
)
_GLOBAL = re.compile(r"(?im)^\s*(?:AUDIO|TEXT RULE|PRODUCT RULE|MOTION RULE|VISUAL STYLE|EDITING / TIMING|STRICT NEGATIVE|PRODUCT CINEMATOGRAPHY LOCK|FINISHING LOCK|CHARACTER CONTINUITY|On-screen copy and graphic direction|Voiceover performance and synchronisation|Camera, lighting and finishing|Music and sound mix|Generation workflow and final checks)\s*[:\n]")


def _clock_seconds(value: str) -> float:
    raw = str(value or "").strip()
    if ":" not in raw:
        return float(raw)
    minutes, seconds = raw.split(":", 1)
    return float(minutes) * 60.0 + float(seconds)


def _session_windows(prompt: str) -> list[tuple[float, float]]:
    return [
        (_clock_seconds(match.group(2)), _clock_seconds(match.group(3)))
        for match in _SESSION_HEADER.finditer(prompt or "")
    ]


def explicit_shot_windows(prompt: str, *, total: float | None = None) -> list[tuple[float, float]]:
    """Return a contiguous authored edit, or leave unstructured briefs as one clip."""
    sessions = _session_windows(prompt)
    if len(sessions) >= 2:
        previous = 0.0
        for a, b in sessions:
            if abs(a - previous) > 0.05 or b <= a or b - a > 15.05:
                raise ValueError(
                    "Seedance sessions must be continuous, ordered, and no longer than 15 seconds."
                )
            previous = b
        if total is not None and abs(previous - total) > 0.05:
            raise ValueError("The session timeline does not cover the requested video duration.")
        return sessions
    windows = []
    for header in SHOT_HEADER.finditer(prompt):
        heading = re.sub(
            r"(?i)^\s*(?:#{1,6}\s*)?(?:(?:CLIP|Scene)\s*\d+|S\d+[A-Za-z]?)\b",
            "",
            header.group(),
        )
        timing = _RANGE.search(heading)
        if not timing:
            return []
        windows.append((_clock_seconds(timing.group(1)), _clock_seconds(timing.group(2))))
    if len(windows) < 2:
        return []
    repaired: list[tuple[float, float]] = []
    for index, (a, b) in enumerate(windows):
        is_last = index == len(windows) - 1
        if b <= a and is_last:
            # Common brief typo on the final CTA line, e.g. "1:31–1:30".
            if total is not None and total > a:
                b = float(total)
            else:
                b = a + 2.0
        repaired.append((a, b))
    windows = repaired
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
        adjustment = float(total) - authored_end
        if adjustment > 0:
            duration_override = (
                f"\nSELECTED-DURATION OVERRIDE: Preserve the authored final-shot action and "
                f"timing, then extend only its stable ending composition by {adjustment:g}s "
                f"to finish at global {float(total):g}s. This overrides older duration words "
                "inside this final scene."
            )
        else:
            duration_override = (
                f"\nSELECTED-DURATION OVERRIDE: Keep the authored final action at natural "
                f"speed and shorten only its stable ending hold by {abs(adjustment):g}s to "
                f"finish at global {float(total):g}s. This overrides older duration words "
                "inside this final scene."
            )
        normalized = (
            candidate[: final_header.start()]
            + replacement
            + duration_override
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
    session_headers = list(_SESSION_HEADER.finditer(prompt))
    if len(session_headers) >= 2:
        prefix = prompt[:session_headers[0].start()].strip()
        selected: list[str] = []
        for i, header in enumerate(session_headers):
            a = _clock_seconds(header.group(2))
            b = _clock_seconds(header.group(3))
            if b <= start or a >= end:
                continue
            stop = session_headers[i + 1].start() if i + 1 < len(session_headers) else len(prompt)
            body = prompt[header.end():stop].strip()
            body = re.split(
                r"(?im)^\s*(?:---\s*)?QC\s+SESSION\b|^\s*STEP\s+[4-9]\s*[—–-]",
                body,
                maxsplit=1,
            )[0].strip()
            selected.append(
                f"SESSION {header.group(1).upper()} — LOCAL 0–{b - a:g} seconds:\n{body}"
            )
        if not selected:
            raise ValueError(
                f"No Seedance session covers {start:g}–{end:g}s. Correct the session timeline."
            )
        context = re.sub(r"\b\d+(?:\.\d+)?[- ]SECOND\b", "FULL-FILM", prefix, flags=re.I)
        return validate_video_prompt(
            f"Generate ONLY {end - start:g} seconds for global timeline {start:g}–{end:g}s "
            f"of a {total:g}s film. This is one complete Seedance call. "
            "Follow the session's local shot timings exactly. Do not render QC, extraction, "
            "stitch, audio-post, caption-post or encode instructions as scene content.\n\n"
            f"{context}\n\n" + "\n\n".join(selected)
        )
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
        heading = re.sub(
            r"(?i)^\s*(?:#{1,6}\s*)?(?:(?:CLIP|Scene)\s*\d+|S\d+[A-Za-z]?)\b",
            "",
            header.group(),
        )
        timing = _RANGE.search(heading)
        a, b = (
            (_clock_seconds(timing.group(1)), _clock_seconds(timing.group(2)))
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
