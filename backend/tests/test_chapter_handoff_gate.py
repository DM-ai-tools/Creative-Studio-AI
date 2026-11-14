"""The chapter handoff check must not reject correct chapters and block the final stitch."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.services.creative_studio_job_service import _chapter_opens_on_scene_cut
from app.services.creative_studio_quality_gate import chapter_quality_report

GATE = "app.services.creative_studio_quality_gate"


def _png(shade: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (96, 96), (shade, shade, shade)).save(buffer, format="PNG")
    return buffer.getvalue()


def _report(previous_url, *, first_frame: bytes, local: Path | None = None, **kwargs):
    with (
        patch(f"{GATE}.probe_video_duration", return_value=6.0),
        patch(f"{GATE}._extract_png_frame", return_value=first_frame),
        patch(f"{GATE}.file_url_to_local_path", return_value=local),
        patch("app.services.ffmpeg_util.require_ffmpeg", return_value="ffmpeg"),
    ):
        return chapter_quality_report(
            Path("chapter.mp4"),
            expected_duration=6.0,
            previous_continuity_url=previous_url,
            references_locked=True,
            **kwargs,
        )


def _handoff(report: dict) -> dict:
    return next(check for check in report["checks"] if check["id"] == "exact_handoff")


def test_mismatched_handoff_still_fails_for_a_continuous_chapter(tmp_path):
    previous = tmp_path / "last.png"
    previous.write_bytes(_png(20))
    report = _report("/files/t/last.png", first_frame=_png(230), local=previous)
    assert report["status"] == "failed"
    assert report["failed_checks"] == ["exact_handoff"]


def test_authored_scene_cut_is_not_rejected(tmp_path):
    previous = tmp_path / "last.png"
    previous.write_bytes(_png(20))
    report = _report(
        "/files/t/last.png", first_frame=_png(230), local=previous, authored_scene_cut=True
    )
    assert report["status"] == "passed"
    assert _handoff(report)["skipped"] is True


def test_remote_provider_frame_is_downloaded_and_compared():
    class _Response:
        content = _png(20)

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            return _Response()

    with patch("httpx.Client", _Client):
        matching = _report("https://provider.test/last.png", first_frame=_png(22))
        different = _report("https://provider.test/last.png", first_frame=_png(230))
    assert matching["status"] == "passed"
    assert "mean_absolute_error" in _handoff(matching)
    assert different["failed_checks"] == ["exact_handoff"]


def test_unreachable_prior_frame_does_not_reject_the_chapter():
    with patch("httpx.Client", side_effect=RuntimeError("network down")):
        report = _report("https://provider.test/expired.png", first_frame=_png(230))
    assert report["status"] == "passed"
    assert _handoff(report)["skipped"] is True


def test_scene_cut_detection_follows_the_script():
    plan = [
        {"scene": 4, "start": 21.0, "end": 29.0, "type": "broll"},
        {"scene": 5, "start": 29.0, "end": 35.0, "type": "broll"},
    ]
    assert _chapter_opens_on_scene_cut(plan, start=29.0, end=35.0) is True
    presenter = [
        {"scene": 1, "start": 0.0, "end": 40.0, "type": "presenter"},
    ]
    assert _chapter_opens_on_scene_cut(presenter, start=30.0, end=40.0) is False
    mid_scene = [{"scene": 1, "start": 20.0, "end": 40.0, "type": "broll"}]
    assert _chapter_opens_on_scene_cut(mid_scene, start=30.0, end=40.0) is False
