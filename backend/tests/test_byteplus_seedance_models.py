import io
import unittest

from PIL import Image

from app.services.creative_studio_job_service import _seedance_segment_durations
from app.services.logo_overlay import pad_image_bytes_for_seedance_reference
from app.services.media.byteplus_seedance_client import (
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

    def test_seedance_20_keeps_four_by_five(self):
        ratio, note = resolve_seedance_api_ratio("4/5", model="ark-seedance-2-0")
        self.assertEqual(ratio, "4:5")
        self.assertIsNone(note)

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
