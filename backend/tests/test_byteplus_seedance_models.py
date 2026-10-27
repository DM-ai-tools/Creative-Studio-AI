import asyncio
import io
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.services.creative_studio_job_service import _seedance_segment_durations
from app.services.logo_overlay import pad_image_bytes_for_seedance_reference
from app.services.media.byteplus_seedance_client import (
    ark_api_key_for_model,
    clamp_seedance_duration,
    create_video_task,
    is_seedance_25_model,
    map_aspect_to_ratio,
    map_resolution,
    resolve_seedance_api_model,
    resolve_seedance_api_ratio,
    seedance_clip_cap_seconds,
)
from app.services.media.byteplus_seedance_provider import resolve_byteplus_api_model


class SeedanceModelTests(unittest.TestCase):
    def test_clip_cap_by_catalog_model(self):
        self.assertEqual(seedance_clip_cap_seconds("ark-seedance-2-0"), 15)
        self.assertEqual(seedance_clip_cap_seconds("ark-seedance-2-5"), 30)

    def test_seedance_25_preserves_requested_whole_second_durations(self):
        for seconds in (21, 23, 30):
            self.assertEqual(
                clamp_seedance_duration(
                    seconds,
                    max_seconds=seedance_clip_cap_seconds("ark-seedance-2-5"),
                    model="dreamina-seedance-2-5-260628",
                ),
                seconds,
            )
        self.assertEqual(
            clamp_seedance_duration(
                15,
                max_seconds=seedance_clip_cap_seconds("ark-seedance-2-0"),
                model="dreamina-seedance-2-0-260128",
            ),
            15,
        )

    def test_create_task_sends_exact_seedance_25_duration(self):
        response = type(
            "Response",
            (),
            {
                "status_code": 200,
                "content": b"{}",
                "json": lambda self: {"id": "task-21"},
                "text": "",
            },
        )()
        request = AsyncMock(return_value=response)
        with patch(
            "app.services.media.byteplus_seedance_client.async_request_with_retry",
            request,
        ):
            task_id = asyncio.run(
                create_video_task(
                    object(),
                    prompt="One continuous 21-second commercial scene.",
                    model="dreamina-seedance-2-5-260628",
                    duration=21,
                    ratio="1:1",
                    resolution="1080p",
                    generate_audio=True,
                )
            )
        self.assertEqual(task_id, "task-21")
        self.assertEqual(request.await_args.kwargs["json"]["duration"], 21)
        self.assertEqual(request.await_args.kwargs["json"]["model"], "dreamina-seedance-2-5-260628")

    def test_resolve_api_models(self):
        self.assertEqual(
            resolve_byteplus_api_model("ark-seedance-2-5"),
            resolve_seedance_api_model("ark-seedance-2-5"),
        )
        self.assertIn("2-5", resolve_byteplus_api_model("ark-seedance-2-5"))

    def test_resolution_caps_for_seedance_25(self):
        self.assertEqual(map_resolution("1080p", model="ark-seedance-2-5"), "1080p")
        self.assertEqual(map_resolution("2k", model="ark-seedance-2-5"), "1080p")
        self.assertEqual(map_resolution("4k", model="ark-seedance-2-0"), "1080p")

    def test_segment_splitting_uses_thirty_second_cap(self):
        self.assertEqual(_seedance_segment_durations(60, 30), [30, 30])
        self.assertEqual(_seedance_segment_durations(60, 15), [15, 15, 15, 15])
        self.assertEqual(_seedance_segment_durations(120, 30), [30, 30, 30, 30])

    def test_is_seedance_25_model(self):
        self.assertTrue(is_seedance_25_model("ark-seedance-2-5"))
        self.assertFalse(is_seedance_25_model("ark-seedance-2-0"))

    def test_api_key_selection_by_model(self):
        from app.core.config import settings

        original_20 = settings.ARK_API_KEY
        original_25 = settings.ARK_API_KEY_25
        try:
            settings.ARK_API_KEY = "key-2-0"
            settings.ARK_API_KEY_25 = "key-2-5"
            self.assertEqual(ark_api_key_for_model("ark-seedance-2-0"), "key-2-0")
            self.assertEqual(ark_api_key_for_model("ark-seedance-2-5"), "key-2-5")
            settings.ARK_API_KEY_25 = ""
            self.assertEqual(ark_api_key_for_model("ark-seedance-2-5"), "key-2-0")
        finally:
            settings.ARK_API_KEY = original_20
            settings.ARK_API_KEY_25 = original_25

    def test_map_aspect_includes_four_by_five(self):
        self.assertEqual(map_aspect_to_ratio("4/5"), "4:5")
        self.assertEqual(map_aspect_to_ratio("4:5"), "4:5")

    def test_seedance_25_maps_four_by_five_to_three_by_four(self):
        ratio, note = resolve_seedance_api_ratio("4/5", model="ark-seedance-2-5")
        self.assertEqual(ratio, "3:4")
        self.assertIn("4:5", note or "")

    def test_seedance_25_first_frame_requires_adaptive(self):
        ratio, note = resolve_seedance_api_ratio(
            "4/5", model="ark-seedance-2-5", frame_locked=True,
        )
        self.assertEqual(ratio, "adaptive")
        self.assertIn("adaptive", note or "")

    def test_seedance_20_maps_four_by_five_to_three_by_four(self):
        ratio, note = resolve_seedance_api_ratio("4/5", model="ark-seedance-2-0")
        self.assertEqual(ratio, "3:4")
        self.assertIn("4:5", note or "")

    def test_pad_wide_reference_for_seedance(self):
        img = Image.new("RGB", (310, 100), color=(20, 120, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        padded = Image.open(io.BytesIO(pad_image_bytes_for_seedance_reference(buf.getvalue())))
        ratio = padded.size[0] / padded.size[1]
        self.assertLessEqual(ratio, 2.50)
        self.assertGreaterEqual(ratio, 0.39)
        self.assertGreaterEqual(min(padded.size), 300)


if __name__ == "__main__":
    unittest.main()
