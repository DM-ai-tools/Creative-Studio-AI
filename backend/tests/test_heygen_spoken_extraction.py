import unittest

from app.services.video_script_skeleton import (
    extract_heygen_spoken_script,
    looks_like_production_brief,
    resolve_heygen_spoken_script,
)

TRAFFIC_RADIUS_BRIEF = """TRAFFIC RADIUS — FREE GOOGLE ADS AUDIT

SCENE 1 — 0:00–0:06 — AVATAR 1 HOOK

VISUAL:
Avatar 1 speaks directly to camera.

SPEAK EXACTLY:
"Hey, e-commerce business owners! Spending five grand or more a month on Google Ads?"

SCENE 2 — 0:06–0:14 — ORIGINAL PERFORMANCE PROOF

VISUAL:
Transition to the original uploaded screenshot.

VOICE-OVER — SAME SELECTED VOICE:
"Across e-commerce campaigns we've managed, thirteen point five eight million dollars in Google Ads spend recorded seventy-one point six four million dollars in tracked conversion value."

SMALL DISCLAIMER:
"Historical Google Ads-reported conversion values. Individual results vary."

SCENE 6 — 0:32–0:35 — FINAL CTA

SPEAK EXACTLY:
"Book your free Google Ads audit now!"

FINAL PRODUCTION RULES:
- Do not read PDF content aloud unless it appears in the approved dialogue.
"""


class HeygenSpokenExtractionTests(unittest.TestCase):
    def test_detects_production_brief(self):
        self.assertTrue(looks_like_production_brief(TRAFFIC_RADIUS_BRIEF))

    def test_extracts_speak_exactly_and_voiceover_only(self):
        spoken = extract_heygen_spoken_script(TRAFFIC_RADIUS_BRIEF, target_seconds=35)
        self.assertIn("Hey, e-commerce business owners", spoken)
        self.assertIn("thirteen point five eight million", spoken)
        self.assertIn("Book your free Google Ads audit now", spoken)
        self.assertIn("Individual results vary", spoken)
        self.assertNotIn("TRAFFIC RADIUS", spoken)
        self.assertNotIn("FINAL PRODUCTION RULES", spoken)
        self.assertNotIn("VISUAL:", spoken)

    def test_resolve_custom_prompt_does_not_read_full_brief(self):
        brief = {
            "key_benefits": {
                "script_source": "custom",
                "custom_prompt": TRAFFIC_RADIUS_BRIEF,
                "avatar_script": TRAFFIC_RADIUS_BRIEF,
            }
        }
        spoken = resolve_heygen_spoken_script(
            brief,
            {},
            production_skeleton=TRAFFIC_RADIUS_BRIEF,
            target_seconds=35,
        )
        self.assertIn("Hey, e-commerce business owners", spoken)
        self.assertNotIn("PRESENTER CONSISTENCY LOCK", spoken)


if __name__ == "__main__":
    unittest.main()
