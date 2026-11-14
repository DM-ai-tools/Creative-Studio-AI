"""Captions and logo are an optional last step on a finished Creative Studio video."""

import pytest

from app.services.creative_studio_caption_logo import (
    _output_size,
    _split_caption_chunks,
    build_caption_ass,
    caption_events_from_script,
    finish_video_with_captions_and_logo,
)

SCRIPT = """SCENE 1 — 0:00–0:05 — PRESENTER
VISUAL: She looks into the camera.
DIALOGUE:
"Hey E-commerce business owners! Your ads aren't failing — your system is."

SCENE 2 — 0:05–0:12 — B-ROLL
VISUAL: Shelves of parcels.
DIALOGUE:
"Without the right funnel, tracking, and creative strategy, scaling stays out of reach."
"""


def test_chunks_are_short_and_keep_every_spoken_word():
    line = "Hey E-commerce business owners! Your ads aren't failing — your system is."
    chunks = _split_caption_chunks(line)
    assert all(len(chunk) <= 26 or len(chunk.split()) == 1 for chunk in chunks)
    assert " ".join(chunks).split() == [word for word in line.split() if word != "—"]


def test_captions_follow_scene_windows_in_order_without_overlap():
    events = caption_events_from_script(SCRIPT, duration_seconds=12)
    assert events and events[0][0] == 0.0
    assert all(end > start for start, end, _ in events)
    assert all(a[1] <= b[0] + 0.001 for a, b in zip(events, events[1:]))
    first_scene = [e for e in events if e[0] < 5.0]
    second_scene = [e for e in events if e[0] >= 5.0]
    assert first_scene[-1][1] <= 5.0 and second_scene[0][0] == 5.0
    assert second_scene[-1][1] <= 12.0


def test_visual_directions_are_never_captioned():
    text = " ".join(chunk for _, _, chunk in caption_events_from_script(SCRIPT, duration_seconds=12))
    assert "camera" not in text and "parcels" not in text


def test_script_without_spoken_lines_gives_no_captions():
    assert caption_events_from_script("Make a nice ad about shoes.", duration_seconds=10) == []


def test_small_provider_video_is_upscaled_and_shape_is_kept():
    assert _output_size(640, 640) == (1080, 1080)
    assert _output_size(480, 854) == (1080, 1922)
    assert _output_size(1080, 1920) == (1080, 1920)


def test_captions_sit_above_the_bottom_edge():
    portrait = build_caption_ass([(0.0, 1.0, "Hello there")], width=1080, height=1920)
    style = next(line for line in portrait.splitlines() if line.startswith("Style: Caption"))
    fields = style.split(",")
    assert fields[18] == "2"  # bottom-centre alignment
    assert int(fields[21]) == round(1920 * 0.15)  # lifted clear of the bottom edge
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,Caption,,0,0,0,,Hello there" in portrait


def test_nothing_selected_is_rejected():
    with pytest.raises(ValueError):
        finish_video_with_captions_and_logo(
            video_url="/files/t/x.mp4", script=SCRIPT, tenant_id="t",
            add_captions=False, add_logo=False,
        )
