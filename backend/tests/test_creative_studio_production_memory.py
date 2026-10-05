"""Regression coverage for the staged-film production lock."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.creative_studio_preflight import validate_video_preflight
from app.services.creative_studio_production_memory import (
    append_chapter_log,
    compile_locked_chapter_prompt,
    create_production_memory,
    ensure_production_memory,
    load_production_memory,
    normalized_reference_lock,
    save_production_memory,
)
from app.services.creative_studio_speech import slice_prepared_narration


PROMPT = """TRAFFIC RADIUS — 90 SECOND FILM
Australian male voice, 145 words per minute.
Scene 1 | 0:00–0:15
Presenter introduces the business problem.
Voiceover, 0–15 seconds: "Start with the business problem and its impact."
Scene 2 | 0:15–0:30
Show proof and ROAS evidence, with no generic walking.
Voiceover, 15–30 seconds: "Now inspect the evidence and return on ad spend."
Scene 3 | 0:30–0:45
Show the strategy funnel from search to checkout.
Scene 4 | 0:45–1:00
Show campaign optimisation work.
Scene 5 | 1:00–1:15
Show measurement and reporting.
Scene 6 | 1:15–1:30
Finish with the audit call to action.
"""


class ProductionMemoryTests(unittest.TestCase):
    def _memory(self):
        references = normalized_reference_lock(
            [
                {"url": "/uploads/scene.png", "role": "scene"},
                {"url": "/uploads/person.png", "role": "character"},
            ],
            product_reference_url=None,
            logo_reference_url="/uploads/logo.png",
        )
        return create_production_memory(
            tenant_id="tenant",
            session_id="chat-1",
            prompt=PROMPT,
            duration_seconds=90,
            clip_cap=15,
            aspect="1/1",
            resolution="1080p",
            model="ark-seedance-2-0",
            brand_name="Traffic Radius",
            product_name="Marketing service",
            voice_events=[
                (0.0, 15.0, "Start with the business problem and its impact."),
                (15.0, 30.0, "Now inspect the evidence and return on ad spend."),
            ],
            references=references,
        )

    def test_six_chapters_share_one_frozen_package(self):
        memory = self._memory()
        self.assertEqual(len(memory["shot_list"]), 6)
        self.assertEqual(memory["voice_lock"]["voice"], "cedar")
        chapter = compile_locked_chapter_prompt(memory, chapter_index=1)
        self.assertIn(memory["production_id"], chapter)
        self.assertIn("global 15-30s", chapter)
        self.assertIn("No generic walking", chapter)
        self.assertIn("provider speech is disabled", chapter)
        self.assertIn("do not speak", chapter.lower())

    def test_reference_change_is_blocked_after_first_accepted_chapter(self):
        memory = self._memory()
        with tempfile.TemporaryDirectory() as folder, patch(
            "app.services.creative_studio_production_memory.settings.UPLOAD_DIR", folder
        ):
            save_production_memory("tenant", memory)
            append_chapter_log(
                "tenant",
                memory,
                chapter_index=0,
                video_url="/uploads/ch1.mp4",
                video_path=str(Path(folder) / "ch1.mp4"),
                duration_seconds=15,
                continuity_frame_url="/uploads/ch1-final.png",
                qa={"status": "passed"},
                provider_task_id="task-1",
            )
            self.assertEqual(len(load_production_memory("tenant", "chat-1")["chapter_log"]), 1)
            changed = normalized_reference_lock(
                [{"url": "/uploads/different-person.png", "role": "character"}],
                product_reference_url=None,
                logo_reference_url="/uploads/logo.png",
            )
            with self.assertRaisesRegex(ValueError, "references are already locked"):
                ensure_production_memory(
                    tenant_id="tenant",
                    session_id="chat-1",
                    prompt="Generate the next part",
                    duration_seconds=90,
                    clip_cap=15,
                    aspect="1/1",
                    resolution="1080p",
                    model="ark-seedance-2-0",
                    brand_name="Traffic Radius",
                    product_name="Marketing service",
                    voice_events=[],
                    references=changed,
                )

    def test_narration_slice_rebases_and_rejects_split_lines(self):
        prepared = {
            "voice": "cedar",
            "lines": [
                {"start": 15.0, "end": 20.0, "text": "Proof first", "path": "a.wav"},
                {"start": 20.0, "end": 30.0, "text": "Then strategy", "path": "b.wav"},
            ],
        }
        events, sliced = slice_prepared_narration(prepared, start=15.0, end=30.0)
        self.assertEqual(events, [(0.0, 5.0, "Proof first"), (5.0, 15.0, "Then strategy")])
        self.assertEqual(sliced["voice"], "cedar")
        with self.assertRaisesRegex(ValueError, "crosses a Seedance chapter boundary"):
            slice_prepared_narration(
                {"lines": [{"start": 14.0, "end": 16.0, "text": "Split", "path": "c.wav"}]},
                start=15.0,
                end=30.0,
            )

    def test_preflight_blocks_unnatural_voice_speed_before_video_call(self):
        with self.assertRaisesRegex(ValueError, "cannot sound natural"):
            validate_video_preflight(
                prompt="Scene 1 | 0:00–0:15\nShow the office.",
                duration_seconds=15,
                storyboard_image_urls=[],
                seed_image_url=None,
                sound_on=True,
                voice_events=[(0.0, 2.0, "one two three four five six seven eight nine ten")],
                reference_assets=[],
                product_reference_url=None,
                logo_reference_url=None,
            )


if __name__ == "__main__":
    unittest.main()
