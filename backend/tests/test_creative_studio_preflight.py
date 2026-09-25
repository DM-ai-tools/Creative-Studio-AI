import unittest

from app.services.creative_studio_preflight import validate_video_preflight
from app.services.creative_studio_picture import compile_picture_prompt, sanitize_visual_direction
from app.services.creative_studio_storyboard import parse_storyboard_scenes, build_storyboard_video_prompt


class CreativeStudioPreflightTests(unittest.TestCase):
    def _prompt(self):
        return "\n".join(
            f"Scene {i + 1} - SHOT {i + 1} | {i * 4}-{(i + 1) * 4} seconds\nAction {i + 1}."
            for i in range(6)
        ) + "\nScene 7 - END | 24-26 seconds\nFinal action."

    def test_valid_timed_storyboard_builds_asset_lock(self):
        report = validate_video_preflight(
            prompt=self._prompt(), duration_seconds=26,
            storyboard_image_urls=[f"/files/scene-{i}.png" for i in range(7)],
            seed_image_url="/files/scene-0.png", sound_on=True,
            voice_events=[(0, 4, "Opening line"), (22, 26, "Final line")],
            reference_assets=[{"url": "/files/person.png", "role": "character"}],
            product_reference_url="/files/product.png", logo_reference_url="/files/logo.png",
        )
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["scene_count"], 7)
        self.assertEqual(report["storyboard_count"], 7)
        self.assertEqual(report["asset_lock"]["logo_rendering"], "post-production composite only")

    def test_stale_extra_storyboard_blocks_before_provider_submission(self):
        with self.assertRaisesRegex(ValueError, "Storyboard coverage mismatch"):
            validate_video_preflight(
                prompt=self._prompt(), duration_seconds=26,
                storyboard_image_urls=[f"/files/scene-{i}.png" for i in range(8)], seed_image_url=None,
                sound_on=False, voice_events=[], reference_assets=[],
                product_reference_url=None, logo_reference_url=None,
            )

    def test_unplanned_long_video_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "explicit timed multi-scene plan"):
            validate_video_preflight(
                prompt="Make a continuous business advertisement.", duration_seconds=30,
                storyboard_image_urls=[], seed_image_url=None, sound_on=False,
                voice_events=[], reference_assets=[], product_reference_url=None,
                logo_reference_url=None,
            )

    def test_picture_prompt_replaces_glossy_ai_words_with_capture_physics(self):
        prompt = compile_picture_prompt(
            "Scene 1 - OPENING | 0-5 seconds\nA stunning photorealistic person holds a box.\n"
            "Scene 2 - END | 5-10 seconds\nShow the uploaded Acme logo.",
            duration=10,
        )
        self.assertNotIn("photorealistic", prompt.lower())
        self.assertNotIn("uploaded acme logo", prompt.lower())
        self.assertIn("35mm lens at f/4", prompt)
        self.assertIn("never pose like catalogue models", prompt)

    def test_ugc_storyboard_uses_phone_capture_language(self):
        scenes = parse_storyboard_scenes(
            "UGC smartphone social video.\nScene 1 - DEMO | 0-5 seconds\n"
            "A woman naturally demonstrates the product in her kitchen.\n"
            "Scene 2 - RESULT | 5-10 seconds\nShe smiles after using it."
        )
        self.assertIn("26mm-equivalent lens", scenes[0]["image_prompt"])
        self.assertNotIn("photoreal", scenes[0]["image_prompt"].lower())

    def test_mixed_logo_clause_does_not_delete_scene_action(self):
        cleaned = sanitize_visual_direction(
            "Create a natural service video in an unfinished backyard, using the uploaded "
            "Fence Guru logo as the exact original brand logo. VIDEO SPECIFICATIONS: 26 seconds."
        )
        self.assertIn("unfinished backyard", cleaned.lower())
        self.assertNotIn("logo", cleaned.lower())
        self.assertNotIn("video specifications", cleaned.lower())

    def test_storyboard_video_prompt_never_asks_model_to_render_copy(self):
        prompt = build_storyboard_video_prompt([
            {"title": "0-5 seconds", "visual": "A woman enters the room", "overlays": ["Hello World"]}
        ])
        self.assertNotIn("Hello World", prompt)
        self.assertIn("composited in post-production", prompt)

    def test_picture_sanitizer_preserves_final_cta_scene_timing(self):
        from app.services.creative_studio_timeline import explicit_shot_windows

        brief = (
            "SCENE 1 - OPENING | 0-22 SECONDS\nShow the full story.\n"
            "SCENE 2 - FINAL BRAND REVEAL + CTA | 22-26 SECONDS\n"
            "Hold the finished property in a clean composition."
        )
        picture = compile_picture_prompt(brief, duration=26)
        self.assertEqual(explicit_shot_windows(picture, total=26)[-1], (22.0, 26.0))

    def test_sectioned_scene_sends_only_visual_direction_to_storyboard(self):
        scenes = parse_storyboard_scenes(
            "Create a video for **Acme Fencing**.\n"
            "Scene 1 - OPENING | 0-5 seconds\nVISUAL DIRECTION:\n"
            "A homeowner studies an unfinished yard.\nVOICEOVER:\n"
            "\u201cPlan your project.\u201d\nON-SCREEN TEXT:\n\u201cStart here\u201d"
        )
        self.assertIn("unfinished yard", scenes[0]["visual"])
        self.assertNotIn("Plan your project", scenes[0]["visual"])
        self.assertNotIn("Start here", scenes[0]["visual"])
        self.assertEqual(scenes[0]["overlays"], ["Start here"])


if __name__ == "__main__":
    unittest.main()
