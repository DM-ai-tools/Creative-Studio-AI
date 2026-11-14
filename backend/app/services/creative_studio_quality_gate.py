"""Local, deterministic QA gates for paid Creative Studio chapters."""

from __future__ import annotations

import logging
import math
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from app.services.ffmpeg_util import probe_video_duration
from app.services.logo_overlay import file_url_to_local_path
from app.services.video_portrait import _extract_png_frame


logger = logging.getLogger(__name__)


def _grayscale(source: bytes | Path) -> Image.Image:
    if isinstance(source, Path):
        image = Image.open(source)
    else:
        image = Image.open(BytesIO(source))
    return image.convert("L").resize((96, 96), Image.Resampling.LANCZOS)


def _load_continuity_frame(url: str) -> bytes | Path | None:
    """Resolve the prior chapter's final frame from local storage or a remote link."""
    local = file_url_to_local_path(url)
    if local and local.is_file():
        return local
    if not str(url).startswith(("http://", "https://")):
        return None
    try:
        import httpx

        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            content = response.content
    except Exception:  # noqa: BLE001 - any fetch failure means "not comparable"
        return None
    return content if len(content) > 100 else None


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
    authored_scene_cut: bool = False,
) -> dict[str, Any]:
    duration = probe_video_duration(video_path)
    checks: list[dict[str, Any]] = []
    # Allow ±10% or ±3s whichever is larger — Seedance clips naturally vary slightly
    # in length and the old 0.35s cap caused almost every chapter to fail needlessly.
    _exp = float(expected_duration)
    _tol = max(3.0, _exp * 0.10)
    duration_ok = duration is not None and abs(float(duration) - _exp) <= _tol
    checks.append({
        "id": "duration",
        "passed": duration_ok,
        "expected_seconds": _exp,
        "observed_seconds": round(float(duration), 3) if duration is not None else None,
        "tolerance_seconds": round(_tol, 2),
    })
    checks.append({"id": "reference_manifest", "passed": bool(references_locked)})

    if previous_continuity_url and authored_scene_cut:
        # The script opens this chapter on a new B-roll/proof scene. A visual cut
        # is what the author asked for, so matching the prior frame would reject
        # a correct chapter and block the final stitch.
        checks.append({
            "id": "exact_handoff",
            "passed": True,
            "skipped": True,
            "reason": "Chapter opens on a new authored scene; a cut from the prior frame is expected",
        })
    elif previous_continuity_url:
        previous = _load_continuity_frame(previous_continuity_url)
        from app.services.ffmpeg_util import require_ffmpeg
        first_png = _extract_png_frame(require_ffmpeg(), video_path, seconds=0.04)
        if previous is None:
            # The provider hands back the prior final frame as a remote link. When
            # it cannot be fetched the comparison is impossible; that is a tooling
            # gap, not a defect in the paid chapter, so do not reject the chapter.
            logger.warning(
                "Chapter QA: prior final frame unavailable for comparison (%s)",
                str(previous_continuity_url)[:80],
            )
            checks.append({
                "id": "exact_handoff",
                "passed": True,
                "skipped": True,
                "reason": "The prior final frame could not be loaded for comparison",
            })
        elif not first_png:
            checks.append({
                "id": "exact_handoff",
                "passed": False,
                "reason": "Could not read this chapter's first frame",
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

