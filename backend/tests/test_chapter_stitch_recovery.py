"""Earlier chapters must be recovered or reported — never silently dropped from the final stitch."""

from pathlib import Path
from unittest.mock import patch

from app.services.creative_studio_job_service import _recover_prior_chapter_paths


def _clip(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"video")
    return path


def test_complete_accumulated_paths_are_left_alone(tmp_path):
    first = _clip(tmp_path, "chapter1.mp4")
    paths, missing = _recover_prior_chapter_paths(
        [first], {"chapter_log": []}, expected_count=1, tenant_id="t"
    )
    assert paths == [first]
    assert missing == []


def test_first_chapter_needs_no_earlier_clips():
    paths, missing = _recover_prior_chapter_paths([], None, expected_count=0, tenant_id="t")
    assert paths == []
    assert missing == []


def test_lost_paths_are_recovered_in_order_from_the_chapter_log(tmp_path):
    first = _clip(tmp_path, "chapter1.mp4")
    second = _clip(tmp_path, "chapter2.mp4")
    memory = {
        "chapter_log": [
            {"chapter": 2, "video_path": str(second)},
            {"chapter": 1, "video_path": str(first)},
        ]
    }
    paths, missing = _recover_prior_chapter_paths([], memory, expected_count=2, tenant_id="t")
    assert paths == [first, second]
    assert missing == []


def test_missing_local_file_is_downloaded_from_the_provider(tmp_path):
    downloaded = _clip(tmp_path, "redownloaded.mp4")
    memory = {
        "chapter_log": [
            {
                "chapter": 1,
                "video_path": str(tmp_path / "gone.mp4"),
                "provider_video_url": "https://provider.test/chapter1.mp4",
            }
        ]
    }
    with patch(
        "app.services.video_subtitles._ensure_local_video", return_value=downloaded
    ) as fetch:
        paths, missing = _recover_prior_chapter_paths([], memory, expected_count=1, tenant_id="t")
    fetch.assert_called_once_with("https://provider.test/chapter1.mp4", tenant_id="t")
    assert paths == [downloaded]
    assert missing == []


def test_unrecoverable_chapter_is_reported(tmp_path):
    second = _clip(tmp_path, "chapter2.mp4")
    memory = {
        "chapter_log": [
            {"chapter": 1, "video_path": str(tmp_path / "gone.mp4")},
            {"chapter": 2, "video_path": str(second)},
        ]
    }
    paths, missing = _recover_prior_chapter_paths([], memory, expected_count=2, tenant_id="t")
    assert missing == [1]
    assert paths == []
