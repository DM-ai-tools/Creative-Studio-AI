import unittest

from app.services.creative_studio_timeline import explicit_shot_windows, segment_motion_prompt
from app.services.creative_studio_video_finishing import extract_overlay_events, extract_voiceover_events
from app.services.creative_studio_job_service import _localize_timed_events

GARAGE_PROMPT = """15-Second Garage Organization Advertisement
Total Duration: 15 seconds
Format: 9:16 vertical

PART 1 - GENERATE FIRST (0-8 SECONDS)
Scene 1 - Messy Garage (0-3 seconds)
On-screen text: "Stop letting your garage look like a storage dump."
Scene 2 - Transformation (3-5 seconds)
A person snaps their fingers.
Scene 3 - Organized Garage Reveal (5-8 seconds)
Hold the final composition briefly.

PART 2 - GENERATE AFTER APPROVING PART 1 (8-15 SECONDS)
Scene 4 - Product Showcase (0-4 seconds of Part 2)
Voice-over: "Discover heavy-duty storage that fits your space."
Scene 5 - Final Hero Shot and CTA (4-7 seconds of Part 2)
Voice-over: "Shop garage essentials with fast Aussie delivery!"
On-screen text:
"Turn Chaos Into Organized Calm"
"SHOP GARAGE ESSENTIALS"
"Fast Aussie Delivery"
"""

class PartLocalTimelineTests(unittest.TestCase):
    def test_part_local_scene_times_are_mapped_to_global_timeline(self):
        self.assertEqual(
            explicit_shot_windows(GARAGE_PROMPT, total=15),
            [(0.0, 3.0), (3.0, 5.0), (5.0, 8.0), (8.0, 12.0), (12.0, 15.0)],
        )

    def test_second_part_segment_contains_only_second_part_scenes(self):
        segment = segment_motion_prompt(GARAGE_PROMPT, start=8, end=15, total=15)
        normalized = segment.replace("\N{EN DASH}", "-")
        self.assertIn("Product Showcase", normalized)
        self.assertIn("Final Hero Shot and CTA", normalized)
        self.assertNotIn("Messy Garage", normalized)
        self.assertIn("LOCAL 0-4 seconds", normalized)
        self.assertIn("LOCAL 4-7 seconds", normalized)

    def test_part_local_voice_and_text_use_global_times(self):
        self.assertEqual(
            extract_voiceover_events(GARAGE_PROMPT, duration_seconds=15),
            [
                (8.0, 12.0, "Discover heavy-duty storage that fits your space."),
                (12.0, 15.0, "Shop garage essentials with fast Aussie delivery!"),
            ],
        )
        self.assertEqual(
            extract_overlay_events(GARAGE_PROMPT),
            [
                (0.0, 3.0, "Stop letting your garage look like a storage dump."),
                (12.0, 15.0, r"Turn Chaos Into Organized Calm\NSHOP GARAGE ESSENTIALS\NFast Aussie Delivery"),
            ],
        )

    def test_second_part_finishing_events_are_rebased_to_the_clip_clock(self):
        events = extract_overlay_events(GARAGE_PROMPT)
        self.assertEqual(
            _localize_timed_events(events, start=8, end=15),
            [
                (4.0, 7.0, r"Turn Chaos Into Organized Calm\NSHOP GARAGE ESSENTIALS\NFast Aussie Delivery"),
            ],
        )

if __name__ == "__main__":
    unittest.main()
