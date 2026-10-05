"""Local, deterministic QA gates for paid Creative Studio chapters."""

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from app.services.ffmpeg_util import probe_video_duration
from app.services.logo_overlay import file_url_to_local_path
from app.services.video_portrait import _extract_png_frame


def _grayscale(source: bytes | Path) -> Image.Image:
    if isinstance(source, Path):
        image = Image.open(source)
    else:
        image = Image.open(BytesIO(source))
    return image.convert("L").resize((96, 96), Image.Resampling.LANCZOS)


def _histogram_cosine(a: Image.Image, b: Image.Image) -> float:
    ah, bh = a.histogram(), b.histogram()
    dot = sum(float(x) * float(y) for x, y in zip(ah, bh))
    left = math.sqrt(sum(float(x) * float(x) for x in ah))
    right = math.sqrt(sum(float(y) * float(y) for y in bh))
    return dot / (left * right) if left and right else 0.0


def chapter_quality_report(
    video_path: Path,
    *,
    expected_duration: float,
    previous_continuity_url: str | None,
    references_locked: bool,
) -> dict[str, Any]:
    duration = probe_video_duration(video_path)
    checks: list[dict[str, Any]] = []
    duration_ok = duration is not None and abs(float(duration) - float(expected_duration)) <= 0.35
    checks.append({
        "id": "duration",
        "passed": duration_ok,
        "expected_seconds": float(expected_duration),
        "observed_seconds": round(float(duration), 3) if duration is not None else None,
    })
    checks.append({"id": "reference_manifest", "passed": bool(references_locked)})

    if previous_continuity_url:
        previous = file_url_to_local_path(previous_continuity_url)
        from app.services.ffmpeg_util import require_ffmpeg
        first_png = _extract_png_frame(require_ffmpeg(), video_path, seconds=0.04)
        if not previous or not previous.is_file() or not first_png:
            checks.append({
                "id": "exact_handoff",
                "passed": False,
                "reason": "Could not compare the prior final frame with this chapter's first frame",
            })
        else:
            try:
                a, b = _grayscale(previous), _grayscale(first_png)
                difference = ImageChops.difference(a, b)
                mae = sum(difference.getdata()) / (96 * 96 * 255.0)
                histogram = _histogram_cosine(a, b)
                passed = mae <= 0.24 or histogram >= 0.92
                checks.append({
                    "id": "exact_handoff",
                    "passed": passed,
                    "mean_absolute_error": round(mae, 4),
                    "histogram_similarity": round(histogram, 4),
                    "threshold": "MAE <= 0.24 or histogram similarity >= 0.92",
                })
            except (OSError, ValueError):
                checks.append({
                    "id": "exact_handoff",
                    "passed": False,
                    "reason": "The continuity or opening frame is not a readable image",
                })

    failed = [check for check in checks if not check.get("passed")]
    return {
        "status": "passed" if not failed else "failed",
        "checks": checks,
        "failed_checks": [check.get("id") for check in failed],
    }

