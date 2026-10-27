from pathlib import Path
from types import SimpleNamespace

from app.services.video_script_skeleton import detect_insert_stat_segments_by_image_index
from app.services.video_logo_overlay import finalize_video_with_brand_logo
from app.services.video_stats_overlay import burn_stats_images_on_video_file


def test_explicit_stat_marker_can_preserve_the_exact_full_range():
    script = "[00:20 - 00:30] [INSERT STAT IMAGE 1] Show the supplied dashboard"

    assert detect_insert_stat_segments_by_image_index(
        script,
        1,
        duration=60,
        preserve_explicit_times=True,
    ) == [(20.0, 30.0)]


def test_stats_image_replaces_the_full_picture(monkeypatch, tmp_path: Path):
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(
        "app.services.video_stats_overlay.require_ffmpeg",
        lambda: "ffmpeg",
    )
    monkeypatch.setattr(
        "app.services.video_stats_overlay._video_dimensions",
        lambda _path: (1920, 1080),
    )

    def fake_run(command, **_kwargs):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("app.services.video_stats_overlay.subprocess.run", fake_run)

    burn_stats_images_on_video_file(
        tmp_path / "master.mp4",
        [tmp_path / "dashboard.png"],
        tmp_path / "finished.mp4",
        segments=[(20.0, 30.0)],
    )

    command = captured["command"]
    graph = command[command.index("-filter_complex") + 1]
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in graph
    assert "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black" in graph
    assert "overlay=0:0:enable='between(t,20.00,30.00)'" in graph


def test_stats_image_is_the_final_visual_layer(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.services.video_logo_overlay.video_logo_overlay_enabled",
        lambda _brief: True,
    )

    def fake_logo(url, *_args, **_kwargs):
        calls.append(("logo", url))
        return "logo.mp4", True

    def fake_subtitles(url, *_args, **_kwargs):
        calls.append(("subtitles", url))
        return "subtitles.mp4", True

    def fake_stats(url, **_kwargs):
        calls.append(("stats", url))
        return "stats.mp4", True, {"stats_overlay_segments": [(20.0, 30.0)]}

    monkeypatch.setattr(
        "app.services.video_logo_overlay.apply_logo_overlay_to_video_file",
        fake_logo,
    )
    monkeypatch.setattr(
        "app.services.video_subtitles.apply_spoken_subtitles_to_video_file",
        fake_subtitles,
    )
    monkeypatch.setattr(
        "app.services.video_subtitles.subtitles_enabled",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "app.services.video_script_skeleton.resolve_stats_image_urls",
        lambda _brief: ["/files/dashboard.png"],
    )
    monkeypatch.setattr(
        "app.services.video_script_skeleton.resolve_timed_script_for_stats_overlay",
        lambda _brief, _result: "[00:20 - 00:30] [INSERT STAT IMAGE 1]",
    )
    monkeypatch.setattr(
        "app.services.video_stats_overlay.apply_stats_overlay_to_video_file",
        fake_stats,
    )

    result = finalize_video_with_brand_logo(
        {"status": "done", "url": "master.mp4", "provider": "heygen"},
        brief={"heygen_settings": {"captions": True}},
        format_type="video",
        tenant_id="tenant-1",
        logo_url="/files/logo.png",
        spoken_script="The supplied dashboard shows the result.",
        duration_seconds=30,
    )

    assert calls == [
        ("logo", "master.mp4"),
        ("subtitles", "logo.mp4"),
        ("stats", "subtitles.mp4"),
    ]
    assert result["url"] == "stats.mp4"
    assert result["stats_overlay_applied"] is True
