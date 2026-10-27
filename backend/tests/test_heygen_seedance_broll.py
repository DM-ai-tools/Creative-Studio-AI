from app.services.media.heygen_provider import (
    _cinematic_avatar_payload,
    _cinematic_aspect_ratio,
    _seedance_broll_segments,
    heygen_seedance2_enabled,
)


def _brief(scene_map: str, enabled: bool = True) -> dict:
    return {
        "key_benefits": {
            "heygen_settings": {
                "seedance_2_enabled": enabled,
                "scene_broll_directions": scene_map,
            }
        }
    }


def test_seedance_toggle_defaults_to_false():
    assert heygen_seedance2_enabled({}) is False
    assert heygen_seedance2_enabled(_brief("", enabled=False)) is False
    assert heygen_seedance2_enabled(_brief("")) is True


def test_broll_parser_selects_only_broll_and_preserves_times():
    brief = _brief(
        "[00:00-00:07] PRESENTER — speaking to camera\n"
        "[00:07-00:13] B-ROLL — Same presenter walks through the agency\n"
        "[00:13-00:20] PRESENTER — speaking to camera"
    )
    assert _seedance_broll_segments(brief, target_duration=20) == [
        {
            "start": 7.0,
            "end": 13.0,
            "duration": 6,
            "direction": "Same presenter walks through the agency",
        }
    ]


def test_broll_parser_reads_the_single_main_video_prompt():
    brief = {
        "avatar_script": (
            '[00:00-00:06] PRESENTER — SPEAK: "Opening line"\n'
            "[00:06-00:12] B-ROLL — SAME AVATAR walks through the office\n"
            '[00:12-00:18] PRESENTER — SPEAK: "Proof line"'
        ),
        "key_benefits": {
            "heygen_settings": {
                "seedance_2_enabled": True,
                "scene_broll_directions": "",
            }
        },
    }
    assert _seedance_broll_segments(brief, target_duration=18) == [
        {
            "start": 6.0,
            "end": 12.0,
            "duration": 6,
            "direction": "SAME AVATAR walks through the office",
        }
    ]


def test_broll_parser_accepts_common_scene_formats():
    prompts = [
        "Scene 2 — B-ROLL | 5–12 seconds | Same avatar walks through the office",
        "BROLL (5s–12s): Same avatar walks through the office",
        "Scene 2 | 00:05 to 00:12 | CUTAWAY: Same avatar walks through the office",
        "S2 | 5.0–12.0s | CINEMATIC SCENE — Same avatar walks through the office",
    ]
    for prompt in prompts:
        segments = _seedance_broll_segments(
            {"avatar_script": prompt},
            target_duration=15,
        )
        assert len(segments) == 1
        assert segments[0]["start"] == 5.0
        assert segments[0]["end"] == 12.0
        assert "Same avatar walks through the office" in segments[0]["direction"]


def test_broll_parser_distinguishes_speaking_and_visual_labels():
    brief = {
        "avatar_script": (
            "Scene 1 | 0-5 seconds | Avatar speaks to camera: Opening line\n"
            "Scene 2 | 5-10 seconds | Visual direction: Same avatar reviews a campaign\n"
            "Scene 3 | 10-15 seconds | Talking head: Closing line"
        )
    }
    assert _seedance_broll_segments(brief, target_duration=15) == [
        {
            "start": 5.0,
            "end": 10.0,
            "duration": 5,
            "direction": "Same avatar reviews a campaign",
        }
    ]


def test_broll_parser_splits_long_intervals_without_exceeding_15_seconds():
    segments = _seedance_broll_segments(
        _brief("[00:00-00:31] B-roll: Same presenter tours the factory"),
        target_duration=31,
    )
    assert len(segments) == 3
    assert segments[0]["start"] == 0.0
    assert segments[-1]["end"] == 31.0
    assert all(4 <= item["duration"] <= 15 for item in segments)
    assert all(item["end"] - item["start"] <= 15 for item in segments)


def test_broll_parser_clamps_to_video_duration():
    segments = _seedance_broll_segments(
        _brief("[00:27-00:40] B-ROLL — Same presenter closes the office"),
        target_duration=30,
    )
    assert segments[0]["start"] == 27.0
    assert segments[0]["end"] == 30.0
    assert segments[0]["duration"] == 4


def test_cinematic_aspect_ratio_uses_output_format():
    assert _cinematic_aspect_ratio("video", {}) == "16:9"
    assert _cinematic_aspect_ratio("reel", {}) == "9:16"
    assert _cinematic_aspect_ratio("square", {}) == "1:1"


def test_cinematic_avatar_uses_official_v3_payload():
    payload = _cinematic_avatar_payload(
        avatar_id="look-12345678901234567890",
        direction="The presenter walks through a modern office",
        duration_seconds=10,
        aspect_ratio="16:9",
    )
    assert payload["type"] == "cinematic_avatar"
    assert payload["avatar_id"] == ["look-12345678901234567890"]
    assert payload["resolution"] == "1080p"
    assert payload["aspect_ratio"] == "16:9"
    assert payload["duration"] == 10
    assert "does not speak" in payload["prompt"]
