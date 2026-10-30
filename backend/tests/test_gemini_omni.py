from app.services.creative_studio_job_service import (
    _gemini_chapter_durations,
    _restore_failed_gemini_continuation,
    _seedance_segment_durations,
    _video_job_result_payload,
)
from app.services.media.gemini_omni_catalog import (
    GEMINI_OMNI_MODEL_ID,
    gemini_omni_video_catalog_options,
)
from app.services.media.gemini_omni_provider import (
    _aspect_for,
    _interaction_request_body,
    _resolution_for,
    _usage_cost,
    _video_content,
    clamp_gemini_omni_duration,
    is_gemini_omni_model,
)
import pytest

from app.services.usage_tracker import estimate_media_cost


def test_gemini_omni_catalog_is_visible_before_key_configuration():
    options = gemini_omni_video_catalog_options()
    assert len(options) == 1
    assert options[0].id == GEMINI_OMNI_MODEL_ID
    assert options[0].max_duration_seconds == 10


def test_normalize_timeline_avoids_shot_timing_block_for_part_based_briefs():
    from app.services.creative_studio_preflight import validate_video_preflight
    from app.services.creative_studio_timeline import normalize_video_timeline_prompt

    brief = (
        "PART 1 — OPEN (0–8 SECONDS)\nScene 1 — 0:00–0:08\nA\n"
        "PART 2 — PROOF (8–16 SECONDS)\nScene 2 — 0:08–0:16\nB\n"
        "PART 3 — GUIDE (16–24 SECONDS)\nScene 3 — 0:16–0:19\nC\n"
        "Scene 4 — 0:19–0:24\nD\n"
        "PART 4 — CTA (24–30 SECONDS)\nScene 5 — 0:24–0:30\nE"
    )
    normalized = normalize_video_timeline_prompt(brief, brief, total=30)
    validate_video_preflight(
        prompt=normalized,
        duration_seconds=30,
        storyboard_image_urls=[],
        seed_image_url="/files/test/avatar.png",
        sound_on=True,
        voice_events=[],
        reference_assets=[{"url": "/files/test/avatar.png", "role": "character"}],
        product_reference_url=None,
        logo_reference_url=None,
        is_chapter=False,
    )


def test_gemini_chapter_durations_follow_authored_scene_parts():
    brief = (
        "Scene 1 — 0:00–0:08\nOpen\n"
        "Scene 2 — 0:08–0:16\nProof\n"
        "Scene 3 — 0:16–0:19\nMid\n"
        "Scene 4 — 0:19–0:24\nGuide\n"
        "Scene 5 — 0:24–0:30\nCTA"
    )
    authored = _gemini_chapter_durations(brief, 30, 10)
    assert sum(authored) == 30
    assert all(3 <= part <= 10 for part in authored)
    assert authored == [8, 8, 8, 6]


@pytest.mark.parametrize(
    "total,expected_sum_parts",
    [(23, 23), (26, 26), (31, 31), (32, 32), (45, 45), (60, 60)],
)
def test_gemini_chapter_durations_support_arbitrary_runtime_without_authored_scenes(
    total, expected_sum_parts
):
    parts = _gemini_chapter_durations("Simple voiceover ad with no scene headers.", total, 10)
    assert sum(parts) == expected_sum_parts
    assert all(3 <= part <= 10 for part in parts)
    assert parts == _seedance_segment_durations(total, 10)


def test_gemini_omni_long_runtime_uses_same_chapter_split_as_seedance():
    gemini_cap = 10
    seedance_cap = 15
    for total in (26, 30, 45, 60):
        gemini_parts = _seedance_segment_durations(total, gemini_cap)
        seedance_parts = _seedance_segment_durations(total, seedance_cap)
        assert sum(gemini_parts) == total
        assert sum(seedance_parts) == total
        assert len(gemini_parts) >= len(seedance_parts)


def test_gemini_omni_duration_and_output_constraints():
    assert clamp_gemini_omni_duration(1) == 3
    assert clamp_gemini_omni_duration(7) == 7
    assert clamp_gemini_omni_duration(30) == 10
    assert _aspect_for("reel", "1:1")[0] == "9:16"
    assert _aspect_for("landscape", "1:1")[0] == "16:9"
    assert _resolution_for("4k")[0] == "4k"
    assert _resolution_for("480p")[0] == "360p"


def test_gemini_omni_video_and_usage_parsing():
    video = {"type": "video", "data": "AAAA"}
    response = {"steps": [{"type": "model_output", "content": [video]}]}
    assert _video_content(response) == video
    prompt, completion, total, cost, estimated = _usage_cost(
        {
            "total_input_tokens": 100,
            "total_output_tokens": 5_792,
            "total_tokens": 5_892,
            "output_tokens_by_modality": [{"modality": "video", "tokens": 5_792}],
        },
        10,
    )
    assert (prompt, completion, total) == (100, 5_792, 5_892)
    assert cost > 0.10
    assert estimated is False


def test_gemini_omni_result_persists_stateful_interaction_id():
    assert is_gemini_omni_model(GEMINI_OMNI_MODEL_ID)
    payload = _video_job_result_payload(
        result={
            "status": "done",
            "url": "/files/chapter.mp4",
            "provider": "google",
            "gemini_interaction_id": "interaction-123",
            "gemini_previous_interaction_id": "interaction-122",
            "continuation_available": True,
        },
        model=GEMINI_OMNI_MODEL_ID,
        seed_url=None,
        generate_duration=10,
        requested_duration=30,
        stitch_note="Chapter ready",
        credits=0,
        out_warn=None,
    )
    assert payload["gemini_interaction_id"] == "interaction-123"
    assert payload["gemini_previous_interaction_id"] == "interaction-122"
    assert payload["continuation_available"] is True


def test_gemini_omni_cost_fallback_is_per_second_without_fake_credits():
    cost, credits = estimate_media_cost(
        provider="google",
        model=GEMINI_OMNI_MODEL_ID,
        duration_seconds=10,
    )
    assert cost == 1.0
    assert credits == 0.0


def test_stateful_continuation_does_not_send_conflicting_video_task():
    body = _interaction_request_body(
        prompt="Continue the same garage with the product showcase.",
        brief={"gemini_previous_interaction_id": "interaction-part-1"},
        source_image_url=None,
        aspect="9:16",
        resolution="720p",
        duration=7,
    )
    assert body["previous_interaction_id"] == "interaction-part-1"
    assert body["input"] == "Continue the same garage with the product showcase."
    assert "generation_config" not in body


def test_failed_second_part_preserves_retry_from_accepted_interaction():
    repaired = _restore_failed_gemini_continuation({
        "status": "failed",
        "payload": {
            "model": GEMINI_OMNI_MODEL_ID,
            "duration_seconds": 15,
            "generated_duration_seconds": 8,
            "gemini_previous_interaction_id": "interaction-part-1",
            "gemini_chapter_index": 1,
        },
        "result": {"status": "failed", "error": "invalid_request"},
    })
    assert repaired["continuation_available"] is True
    assert repaired["completed_segments"] == 1
    assert repaired["segment_count"] == 2
    assert repaired["generated_duration_seconds"] == 8
    assert repaired["gemini_interaction_id"] == "interaction-part-1"
