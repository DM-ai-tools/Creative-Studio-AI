"""Offline regression tests; provider calls are mocked, media is processed by real FFmpeg."""

import asyncio
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace
import wave

import httpx

from app.services.creative_studio_timeline import (
    explicit_shot_windows,
    segment_motion_prompt,
    select_complete_timeline_prompt,
    validate_video_prompt,
)
from app.services.creative_studio_storyboard import parse_storyboard_scenes, build_storyboard_video_prompt
from app.services.creative_studio_video_finishing import (
    extract_voiceover_events, apply_timed_voiceover, plan_requested_voiceover, voiceover_requested,
)
from app.services.creative_studio_prompt_service import build_spoken_voiceover
from app.services.creative_studio_chat_service import _explicit_duration_from_text, _normalize_duration
from app.services.ffmpeg_util import require_ffmpeg, probe_has_audio, probe_video_duration
from app.services.media.seedance_multiscene import (
    build_continuity_contract,
    coalesce_shot_windows,
    concat_video_files,
    conform_shot_duration,
    save_continuity_frame,
    save_privacy_safe_scene_frame,
    _concat_encoded_video_files,
)
from app.services.media.byteplus_seedance_client import create_video_task
from app.services.media.byteplus_usage import video_task_usage


class PromptTests(unittest.TestCase):
    def test_complete_authored_timeline_wins_over_incomplete_rewrite(self):
        authored = (
            "Scene 1 - OPEN | 0-14 seconds\nOpen naturally.\n"
            "Scene 2 - END | 14-26 seconds\nFinish naturally."
        )
        rewrite = (
            "Scene 1 - OPEN | 0-14 seconds\nOpen naturally.\n"
            "Scene 2 - END | 14-25 seconds\nFinish naturally."
        )
        self.assertEqual(
            select_complete_timeline_prompt(authored, rewrite, total=26),
            authored,
        )

    def test_timeline_selector_still_rejects_real_gap(self):
        broken = (
            "Scene 1 - OPEN | 0-10 seconds\nOpen.\n"
            "Scene 2 - END | 11-26 seconds\nFinish."
        )
        with self.assertRaisesRegex(ValueError, "continuous"):
            select_complete_timeline_prompt(broken, broken, total=26)

    def test_timeline_selector_repairs_only_a_rounded_final_boundary(self):
        rounded = (
            "Scene 1 - OPEN | 0-14 seconds\nOpen.\n"
            "Scene 2 - END | 14-30 seconds\nFinish."
        )
        selected = select_complete_timeline_prompt(rounded, rounded, total=26)
        self.assertEqual(explicit_shot_windows(selected, total=26)[-1], (14.0, 26.0))

    def test_timeline_selector_does_not_stretch_a_short_script(self):
        short = (
            "Scene 1 - OPEN | 0-8 seconds\nOpen.\n"
            "Scene 2 - END | 8-15 seconds\nFinish."
        )
        with self.assertRaisesRegex(ValueError, "requested video duration"):
            select_complete_timeline_prompt(short, short, total=26)

    def test_creative_studio_long_video_duration_is_capped_at_two_minutes(self):
        self.assertEqual(_explicit_duration_from_text("Make this 2 minutes"), 120)
        self.assertEqual(_explicit_duration_from_text("Make this 5 minutes"), 120)
        self.assertEqual(_normalize_duration(600, 15), 120)

    def test_short_authored_shots_are_packed_into_fifteen_second_chapters(self):
        windows = [(float(i), float(i + 5)) for i in range(0, 30, 5)]
        self.assertEqual(
            coalesce_shot_windows(windows),
            [(0.0, 15.0), (15.0, 30.0)],
        )

    def test_continuity_contract_has_opening_and_closing_handoffs(self):
        middle = build_continuity_contract(
            segment_index=1,
            segment_count=3,
            start=15,
            end=30,
            total_duration=45,
            has_previous_frame=True,
        )
        self.assertIn("exact final frame of the previous chapter", middle)
        self.assertIn("same people: identical face", middle)
        self.assertIn("stable handoff frame", middle)
        self.assertIn("Chapter 2/3", middle)

    def test_late_scene_survives_and_clips_have_local_timings(self):
        prompt = "Keep the same red bottle.\nCLIP 1 — 0–15 SECONDS: OPENING\n" + "detail " * 850
        prompt += "\nCLIP 2 — 15–30 SECONDS: FINAL_REVEAL\nAUDIO: ambient room."
        first = segment_motion_prompt(prompt, start=0, end=15, total=30)
        last = segment_motion_prompt(prompt, start=15, end=30, total=30)
        self.assertIn("OPENING", first)
        self.assertNotIn("FINAL_REVEAL", first)
        self.assertIn("FINAL_REVEAL", last)
        self.assertNotIn("OPENING", last)
        self.assertIn("LOCAL 0–15 seconds", last)
        self.assertIn("ambient room", first)
        self.assertGreater(len(first), 4000)

    def test_overlapping_scene_is_rebased(self):
        prompt = "CLIP 1 — 0–10 SECONDS: A\nCLIP 2 — 10–30 SECONDS: B"
        self.assertIn("LOCAL 0–15 seconds", segment_motion_prompt(prompt, start=15, end=30, total=30))

    def test_excessive_prompt_is_rejected_not_sliced(self):
        with self.assertRaises(ValueError):
            validate_video_prompt("x" * 32001)

    def test_generic_story_does_not_invent_farm_or_people(self):
        scenes = parse_storyboard_scenes(
            "Scene 1 — 0-5 seconds: Red headphones on desk\nSlow orbit.\n"
            "Scene 2 — 5-15 seconds: Reveal the charging case\nOpen the lid.",
            product_name="Headphones",
        )
        prompt = build_storyboard_video_prompt(scenes, duration_seconds=15)
        for unwanted in ("chicken", "farm/yard", "adult woman", "wooden coop"):
            self.assertNotIn(unwanted, prompt.lower())
        self.assertIn("Open the lid", prompt)
        self.assertIn("0.0–5.0", prompt)

    def test_more_than_six_scenes_preserved(self):
        scenes = parse_storyboard_scenes("\n".join(
            f"Scene {i}: Product angle {i}\nShow angle {i} carefully." for i in range(1, 9)
        ))
        self.assertEqual(len(scenes), 8)
        self.assertIn("angle 8", build_storyboard_video_prompt(scenes, duration_seconds=60))

    def test_voiceover_formats(self):
        for text in (
            'Voiceover, 0-5 seconds: "Hello there."',
            'VO (0-5s): "Hello there."',
            'Narration: Hello there.',
            'Voice-over: “Hello there.”',
            '0-5s Narrator: Hello there.',
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_voiceover_events(text, duration_seconds=5), [(0.0, 5.0, "Hello there.")])

    def test_voiceover_inherits_scene_window(self):
        text = 'Scene 1 — 0–5 seconds: Hook\nVoiceover: "Hello."\nScene 2 — 5–10 seconds: End\nVO: "Goodbye."'
        self.assertEqual(extract_voiceover_events(text, duration_seconds=10), [
            (0.0, 5.0, "Hello."), (5.0, 10.0, "Goodbye."),
        ])

    def test_no_camera_directions_are_spoken(self):
        self.assertEqual(build_spoken_voiceover("Slow pan around a red bottle."), "")
        self.assertEqual(build_spoken_voiceover('Camera: slow pan\nVoiceover: "Find your rhythm."'), "Find your rhythm.")

    def test_provider_usage_is_not_an_invoice(self):
        usage = video_task_usage({"usage": {"completion_tokens": 1234, "total_tokens": 1234}}, task_id="test", model="seedance")
        self.assertEqual(usage["total_tokens"], 1234)
        self.assertIsNone(usage["cost_usd"])
        self.assertEqual(usage["cost_status"], "unavailable")

    def test_explicit_no_narration_is_respected(self):
        self.assertFalse(voiceover_requested("Music and foley, no voiceover."))
        self.assertTrue(voiceover_requested("Include a warm voiceover about the headphones."))

    def test_timestamp_only_furniture_brief_retains_all_six_shots(self):
        windows = [(0, 2), (2, 3.5), (3.5, 6.5), (6.5, 8.5), (8.5, 11.5), (11.5, 15)]
        brief = "Keep exactly two matching chairs. No armrests.\n" + "\n".join(
            f"{a}–{b} seconds — Shot {i}\nShow action {i}." for i, (a, b) in enumerate(windows)
        )
        # Caption timing lists must not become extra shots.
        brief += '\nOn-screen copy and graphic direction\n0.3–3.2 seconds: "Opening copy."'
        self.assertEqual(explicit_shot_windows(brief, total=15), windows)
        self.assertEqual(len(parse_storyboard_scenes(brief)), 6)
        final = segment_motion_prompt(brief, start=11.5, end=15, total=15)
        self.assertIn("Show action 5", final)
        self.assertNotIn("Show action 0", final)
        self.assertIn("No armrests", final)

    def test_shot_timeline_gaps_fail_before_generation(self):
        with self.assertRaises(ValueError):
            explicit_shot_windows(
                "0–2 seconds — Opening\nA\n3–5 seconds — Finish\nB", total=5
            )

    def test_authored_timeline_can_be_read_before_matching_a_coarse_preset(self):
        brief = (
            "SCENE 1 — CUSTOMER NEED | 0–4 SECONDS\nOpen in a backyard.\n"
            "SCENE 2 — FINAL BRAND REVEAL | 4–26 SECONDS\nHold the CTA."
        )
        self.assertEqual(explicit_shot_windows(brief), [(0.0, 4.0), (4.0, 19.0), (19.0, 26.0)])
        with self.assertRaises(ValueError):
            explicit_shot_windows(brief, total=30)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_reference_image_save_failure_is_not_regenerated(self):
        from app.services.media.openai_image_provider import OpenAIImageProvider

        provider = OpenAIImageProvider()
        persistence_failure = {
            "status": "failed",
            "model": "gpt-image-2",
            "provider": "openai",
            "url": None,
            "error": "generated image could not be saved",
            "retryable": False,
        }
        with (
            patch(
                "app.services.media.openai_image_provider.openai_configured",
                return_value=True,
            ),
            patch.object(
                provider,
                "_generate_with_reference",
                AsyncMock(return_value=persistence_failure),
            ) as edit,
            patch.object(provider, "_post_with_fallbacks", AsyncMock()) as text_fallback,
        ):
            result = await provider.generate(
                prompt="Keep the supplied product exact.",
                tenant_id="test",
                model="openai-gpt-image-2",
                format_type="video",
                reference_image_url="/files/test/product.png",
            )

        self.assertEqual(result, persistence_failure)
        edit.assert_awaited_once()
        text_fallback.assert_not_awaited()

    async def test_requested_narration_without_script_gets_a_spoken_plan(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=json.dumps({
                "lines": [{"start": 0, "end": 5, "text": "Find your rhythm."}]
            })))
        ])
        with (
            patch("app.services.creative_studio_video_finishing.settings.OPENROUTER_API_KEY", "test"),
            patch("app.services.image_prompt_service._get_openrouter_client", return_value=client),
        ):
            lines = await plan_requested_voiceover(
                "Show red headphones. Include a warm voiceover.", duration_seconds=5
            )
        self.assertEqual(lines, [(0.0, 5.0, "Find your rhythm.")])
        self.assertEqual(client.chat.completions.create.call_count, 1)

    async def test_exact_script_does_not_call_a_planner(self):
        with patch("app.services.image_prompt_service._get_openrouter_client") as client:
            lines = await plan_requested_voiceover('Voiceover: "Exact words."', duration_seconds=5)
        client.assert_not_called()
        self.assertEqual(lines, [(0.0, 5.0, "Exact words.")])

    async def test_request_keeps_long_prompt_audio_and_nine_references(self):
        captured = {}
        def respond(request):
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"id": "test-task"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            prompt = "Scene details. " * 500 + "ENDING_AND_VOICEOVER"
            await create_video_task(
                client, prompt=prompt, generate_audio=True,
                extra_image_refs=[{"url": f"https://example.com/{i}.png"} for i in range(9)],
            )
        self.assertEqual(captured["content"][0]["text"], prompt)
        self.assertTrue(captured["generate_audio"])
        self.assertEqual(len(captured["content"]), 10)

    async def test_first_frame_request_never_mixes_reference_media(self):
        captured = {}
        def respond(request):
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"id": "test-task"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            await create_video_task(
                client,
                prompt="Animate the approved scene.",
                image_data_uri_or_url="https://example.com/approved.png",
                image_role="first_frame",
                extra_image_refs=[{"url": "https://example.com/product.png"}],
            )
        image_content = [item for item in captured["content"] if item["type"] == "image_url"]
        self.assertEqual(len(image_content), 1)
        self.assertEqual(image_content[0]["role"], "first_frame")
        self.assertEqual(image_content[0]["image_url"]["url"], "https://example.com/approved.png")


class MediaTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cs_regression_")
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.ffmpeg = require_ffmpeg()
        self.silent = self.make_clip("silent", False)
        self.audible = self.make_clip("audible", True)

    def make_clip(self, name, audio, duration=2):
        target = self.work / f"{name}.mp4"
        command = [self.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=128x96:r=24"]
        if audio:
            command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
        command += ["-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if audio:
            command += ["-c:a", "aac"]
        subprocess.run(command + [str(target)], capture_output=True, check=True, timeout=30)
        return target

    def test_upload_write_probe_succeeds_before_paid_generation(self):
        from app.services.file_service import file_service

        with patch.object(file_service, "upload_dir", self.work):
            file_service.assert_writable("tenant", "generated")
        target = self.work / "tenant" / "generated"
        self.assertTrue(target.is_dir())
        self.assertEqual(list(target.glob(".write-probe-*.tmp")), [])

    def test_upload_write_probe_reports_permission_failure(self):
        from app.services.file_service import file_service

        with (
            patch.object(file_service, "upload_dir", self.work),
            patch("pathlib.Path.write_bytes", side_effect=PermissionError("denied")),
        ):
            with self.assertRaisesRegex(PermissionError, "cannot write to the upload folder"):
                file_service.assert_writable("tenant", "generated")

    def test_ffmpeg_only_audio_detection(self):
        with patch("app.services.ffmpeg_util.ffprobe_executable", return_value=None):
            self.assertTrue(probe_has_audio(self.audible))
            self.assertFalse(probe_has_audio(self.silent))

    def test_stitch_silent_first_preserves_later_sound(self):
        output = self.work / "stitched.mp4"
        concat_video_files([self.silent, self.audible], output)
        self.assertTrue(probe_has_audio(output))
        self.assertAlmostEqual(probe_video_duration(output), 4, delta=0.2)
        measured = subprocess.run([
            self.ffmpeg, "-hide_banner", "-ss", "2.5", "-i", str(output),
            "-af", "volumedetect", "-vn", "-f", "null", "-",
        ], capture_output=True, text=True, timeout=30)
        self.assertIn("mean_volume:", measured.stderr)
        self.assertNotIn("mean_volume: -inf", measured.stderr)

    def test_single_partial_clip_creates_nested_stitch_output(self):
        output = self.work / "missing" / "seedance-stitch" / "partial.mp4"
        concat_video_files([self.audible], output)
        self.assertTrue(output.is_file())
        self.assertAlmostEqual(probe_video_duration(output), 2.0, delta=0.08)

    def test_shot_is_edited_to_fractional_timing(self):
        edited = conform_shot_duration(self.audible, self.work / "shot.mp4", 1.5)
        self.assertTrue(probe_has_audio(edited))
        self.assertAlmostEqual(probe_video_duration(edited), 1.5, delta=0.08)

    def test_short_provider_clip_keeps_normal_speed_for_continuation(self):
        output = self.work / "must-not-be-stretched.mp4"
        edited = conform_shot_duration(self.audible, output, 3.5)
        self.assertEqual(edited, self.audible)
        self.assertFalse(output.exists())
        self.assertTrue(probe_has_audio(edited))
        self.assertAlmostEqual(probe_video_duration(edited), 2.0, delta=0.08)

    def test_last_frame_is_saved_as_a_compact_continuity_reference(self):
        from app.services.file_service import file_service

        with patch.object(file_service, "upload_dir", self.work):
            url = save_continuity_frame(self.audible, tenant_id="test")
        self.assertTrue(url.startswith("/files/test/generated/continuity/"))
        saved = self.work / url.removeprefix("/files/")
        self.assertTrue(saved.is_file())
        self.assertGreater(saved.stat().st_size, 100)

    def test_privacy_safe_handoff_excludes_the_upper_portrait_area(self):
        from app.services.file_service import file_service
        from PIL import Image

        with patch.object(file_service, "upload_dir", self.work):
            url = save_privacy_safe_scene_frame(self.audible, tenant_id="test")
        saved = self.work / url.removeprefix("/files/")
        with Image.open(saved) as image:
            self.assertGreater(image.width, image.height)
            self.assertLess(image.height, 200)

    def test_valid_stitch_survives_empty_late_ffmpeg_error(self):
        output = self.work / "valid-after-late-error.mp4"
        _concat_encoded_video_files([self.audible, self.audible], output)
        self.assertAlmostEqual(probe_video_duration(output), 4.0, delta=0.2)
        real_run = subprocess.run

        def report_late_error(command, *args, **kwargs):
            completed = real_run(command, *args, **kwargs)
            if "concat" in command:
                completed.returncode = 1
                completed.stderr = ""
            return completed

        with patch(
            "app.services.media.seedance_multiscene.subprocess.run",
            side_effect=report_late_error,
        ):
            _concat_encoded_video_files([self.audible, self.audible], output)
        self.assertAlmostEqual(probe_video_duration(output), 4.0, delta=0.2)

    async def test_complete_storyboard_anchors_every_authored_scene(self):
        from app.services.creative_studio_job_service import create_job, run_creative_studio_job, get_job
        from app.services.file_service import file_service

        fixture = self.make_clip("provider-fifteen-second-chapter", True, duration=15)
        provider = Mock()
        provider.generate = AsyncMock(return_value={
            "status": "done", "url": "fixture.mp4", "provider": "byteplus",
            "model": "ark-seedance-2-0", "duration_seconds": 15,
        })
        job_id = await create_job(tenant_id="test", payload={
            "media_mode": "video",
            "model": "ark-seedance-2-0",
            "prompt": (
                "Scene 1 - OPENING | 0-6 seconds\nEstablish the approved location.\n"
                "Scene 2 - PRODUCT | 6-12 seconds\nContinue the product story.\n"
                "Scene 3 - RESULT | 12-18 seconds\nReveal the finished result."
            ),
            "duration_seconds": 18,
            "sound_on": False,
            "brand_name": "Example Brand",
            "seed_image_url": "/files/test/opening.png",
            "logo_reference_url": "/files/test/official-logo.png",
            "reference_assets": [
                {"url": "/files/test/official-logo.png", "role": "logo"},
            ],
            "storyboard_image_urls": [
                "/files/test/chapter-1.png",
                "/files/test/chapter-2.png",
                "/files/test/chapter-3.png",
            ],
        })
        with (
            patch("app.services.media.registry.get_video_provider", return_value=provider),
            patch(
                "app.services.logo_overlay.file_url_to_local_path",
                side_effect=lambda url: fixture if url else None,
            ),
            patch.object(file_service, "upload_dir", self.work),
            patch("app.services.video_subtitles._ensure_local_video", return_value=fixture),
        ):
            await run_creative_studio_job(job_id)

        result = await get_job(job_id)
        self.assertEqual(result["status"], "done", result.get("error"))
        self.assertEqual(provider.generate.await_count, 3)
        first, second, third = provider.generate.call_args_list
        self.assertEqual(first.kwargs["source_image_url"], "/files/test/chapter-1.png")
        self.assertEqual(first.kwargs["brief"]["seed_image_role"], "first_frame")
        self.assertEqual(first.kwargs["brief"]["storyboard_image_urls"], ["/files/test/chapter-1.png"])
        self.assertEqual(second.kwargs["source_image_url"], "/files/test/chapter-2.png")
        self.assertEqual(second.kwargs["brief"]["storyboard_image_urls"], ["/files/test/chapter-2.png"])
        self.assertEqual(third.kwargs["source_image_url"], "/files/test/chapter-3.png")
        self.assertEqual(third.kwargs["brief"]["storyboard_image_urls"], ["/files/test/chapter-3.png"])
        for call in (first, second, third):
            self.assertIsNone(call.kwargs["brief"]["continuity_reference_url"])
            self.assertFalse(call.kwargs["brief"]["strict_continuity_reference"])
            self.assertIn("BRAND-SURFACE LOCK:", call.kwargs["prompt"])
            self.assertIsNone(call.kwargs["brief"]["logo_reference_url"])
            self.assertFalse(any(
                asset.get("role") == "logo"
                for asset in call.kwargs["brief"]["reference_assets"]
            ))
        self.assertFalse(result["continuity_chained"])
        self.assertEqual(result["continuity_frame_count"], 0)
        self.assertTrue(result["storyboard_scene_anchored"])

    async def test_short_provider_media_generates_continuations_without_slow_motion(self):
        from app.services.creative_studio_job_service import create_job, run_creative_studio_job, get_job
        from app.services.file_service import file_service

        eight = self.make_clip("provider-eight-seconds", True, duration=8)
        five = self.make_clip("provider-five-seconds", True, duration=5)
        provider = Mock()
        provider.generate = AsyncMock(side_effect=[
            {"status": "done", "url": "eight-1.mp4", "provider": "byteplus", "model": "ark-seedance-2-0"},
            {"status": "done", "url": "five-1.mp4", "provider": "byteplus", "model": "ark-seedance-2-0"},
            {"status": "done", "url": "eight-2.mp4", "provider": "byteplus", "model": "ark-seedance-2-0"},
            {"status": "done", "url": "five-2.mp4", "provider": "byteplus", "model": "ark-seedance-2-0"},
        ])

        def resolve(url):
            return eight if str(url).startswith("eight-") else five

        job_id = await create_job(tenant_id="test", payload={
            "media_mode": "video",
            "model": "ark-seedance-2-0",
            "prompt": (
                "Scene 1 - FIRST HALF | 0-13 seconds\nContinue the business film.\n"
                "Scene 2 - SECOND HALF | 13-26 seconds\nComplete the business film."
            ),
            "duration_seconds": 26,
            "sound_on": False,
            "seed_image_url": "/files/test/opening.png",
        })
        with (
            patch("app.services.media.registry.get_video_provider", return_value=provider),
            patch("app.services.logo_overlay.file_url_to_local_path", side_effect=resolve),
            patch.object(file_service, "upload_dir", self.work),
            patch("app.services.video_subtitles._ensure_local_video", return_value=eight),
        ):
            await run_creative_studio_job(job_id)

        result = await get_job(job_id)
        self.assertEqual(result["status"], "done", result.get("error"))
        self.assertFalse(result["partial"])
        self.assertEqual(result["duration_seconds"], 26)
        self.assertEqual(result["segment_count"], 4)
        self.assertEqual(provider.generate.await_count, 4)
        calls = provider.generate.call_args_list
        self.assertEqual([call.kwargs["duration_seconds"] for call in calls], [13, 5, 13, 5])
        self.assertIn("CONTINUATION PASS", calls[1].kwargs["prompt"])
        self.assertTrue(calls[1].kwargs["brief"]["strict_continuity_reference"])
        self.assertEqual(calls[0].kwargs["source_image_url"], "/files/test/opening.png")
        self.assertIsNone(calls[1].kwargs["source_image_url"])

    async def test_privacy_block_retries_with_scene_continuity_crop(self):
        from app.services.creative_studio_job_service import create_job, run_creative_studio_job, get_job
        from app.services.file_service import file_service

        fixture = self.make_clip("provider-ten-seconds", True, duration=10)
        provider = Mock()
        provider.generate = AsyncMock(side_effect=[
            {"status": "done", "url": "first.mp4", "provider": "byteplus", "model": "ark-seedance-2-0"},
            {
                "status": "failed", "url": None, "provider": "byteplus",
                "error": "Seedance blocked the previous chapter's continuity frame.",
            },
            {"status": "done", "url": "second.mp4", "provider": "byteplus", "model": "ark-seedance-2-0"},
        ])
        job_id = await create_job(tenant_id="test", payload={
            "media_mode": "video", "model": "ark-seedance-2-0",
            "prompt": (
                "Scene 1 - OPENING | 0-10 seconds\nContinue the business film.\n"
                "Scene 2 - RESULT | 10-20 seconds\nComplete the business film."
            ),
            "duration_seconds": 20, "sound_on": False,
        })
        with (
            patch("app.services.media.registry.get_video_provider", return_value=provider),
            patch(
                "app.services.logo_overlay.file_url_to_local_path",
                side_effect=lambda url: fixture if url else None,
            ),
            patch.object(file_service, "upload_dir", self.work),
            patch("app.services.video_subtitles._ensure_local_video", return_value=fixture),
        ):
            await run_creative_studio_job(job_id)

        result = await get_job(job_id)
        self.assertEqual(result["status"], "done", result.get("error"))
        self.assertEqual(provider.generate.await_count, 3)
        blocked = provider.generate.call_args_list[1].kwargs["brief"]
        retry = provider.generate.call_args_list[2].kwargs["brief"]
        self.assertTrue(blocked["strict_continuity_reference"])
        self.assertIsNotNone(blocked["continuity_reference_url"])
        self.assertFalse(retry["strict_continuity_reference"])
        self.assertIsNone(retry["continuity_reference_url"])
        self.assertIsNone(retry["cast_reference_url"])
        self.assertTrue(any(
            asset.get("role") == "scene" and "continuity-safe" in asset.get("url", "")
            for asset in retry["reference_assets"]
        ))
        self.assertEqual(result["continuity_privacy_fallback_count"], 1)
        self.assertFalse(result["partial"])

    async def test_worker_exposes_missing_audio_and_usage_through_api_schema(self):
        from app.services.creative_studio_job_service import create_job, run_creative_studio_job, get_job
        from app.api.v1.generation import CreativeStudioGenerateResponse
        provider = Mock()
        provider.generate = AsyncMock(return_value={
            "status": "done", "url": "fixture.mp4", "provider": "byteplus",
            "model": "ark-seedance-2-0", "duration_seconds": 2,
            "provider_usage": [{"task_id": "test", "total_tokens": 123, "cost_status": "unavailable"}],
        })
        job_id = await create_job(tenant_id="test", payload={
            "media_mode": "video", "model": "ark-seedance-2-0",
            "prompt": "Show headphones. Natural room sound only.",
            "duration_seconds": 5, "sound_on": True,
        })
        with (
            patch("app.services.file_service.file_service.assert_writable"),
            patch("app.services.media.registry.get_video_provider", return_value=provider),
            patch("app.services.creative_studio_video_finishing.settings.RUNWAYML_API_KEY", ""),
            patch("app.services.video_subtitles._ensure_local_video", return_value=self.silent),
        ):
            await run_creative_studio_job(job_id)
        result = await get_job(job_id)
        self.assertEqual(result["status"], "done", result.get("error"))
        response = CreativeStudioGenerateResponse(**result)
        self.assertFalse(response.audio_present)
        self.assertIn("no audio track", response.audio_warning)
        self.assertEqual(response.provider_usage[0]["total_tokens"], 123)
        self.assertNotIn("Find your rhythm.", provider.generate.call_args.kwargs["prompt"])
        self.assertFalse(provider.generate.call_args.kwargs["brief"]["skip_voiceover"])
        self.assertTrue(provider.generate.call_args.kwargs["brief"]["creative_studio_generate_audio"])

    async def test_six_shot_short_ad_stays_in_one_generation_context(self):
        from app.services.creative_studio_job_service import create_job, run_creative_studio_job, get_job
        fixture = self.make_clip("provider-fifteen-seconds", True, duration=15)
        output = self.work / "assembled.mp4"
        provider = Mock()
        provider.generate = AsyncMock(return_value={
            "status": "done", "url": "fixture.mp4", "provider": "byteplus",
            "model": "ark-seedance-2-0", "duration_seconds": 15,
        })
        windows = [(0, 2), (2, 3.5), (3.5, 6.5), (6.5, 8.5), (8.5, 11.5), (11.5, 15)]
        brief = "Exactly two matching chairs.\n" + "\n".join(
            f"{a}–{b} seconds — Shot {i}\nShow action {i}." for i, (a, b) in enumerate(windows)
        )
        def save(*args, **kwargs):
            output.write_bytes(kwargs.get("content") if "content" in kwargs else args[0])
            return {"file_url": str(output)}
        job_id = await create_job(tenant_id="test", payload={
            "media_mode": "video", "model": "ark-seedance-2-0",
            "prompt": brief, "source_brief": brief, "duration_seconds": 15, "sound_on": True,
        })
        with (
            patch("app.services.media.registry.get_video_provider", return_value=provider),
            patch("app.services.logo_overlay.file_url_to_local_path", return_value=fixture),
            patch("app.services.file_service.file_service.upload_dir", str(self.work)),
            patch("app.services.file_service.file_service.save_bytes", side_effect=save),
            patch("app.services.video_subtitles._ensure_local_video", return_value=fixture),
        ):
            await run_creative_studio_job(job_id)
        result = await get_job(job_id)
        self.assertEqual(result["status"], "done", result.get("error"))
        self.assertEqual(provider.generate.call_count, 1)
        self.assertTrue(result["audio_present"])
        call = provider.generate.call_args
        self.assertEqual(call.kwargs["duration_seconds"], 15)
        for i in range(6):
            self.assertIn(f"Show action {i}", call.kwargs["prompt"])

    async def test_exact_timed_voiceover_is_mixed_and_video_length_preserved(self):
        wav = self.work / "speech.wav"
        with wave.open(str(wav), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(24000)
            stream.writeframes(b"".join(
                struct.pack("<h", int(4000 * math.sin(2 * math.pi * 700 * i / 24000)))
                for i in range(19200)
            ))
        output = self.work / "mixed.mp4"
        def save(content, *args, **kwargs):
            output.write_bytes(content)
            return {"file_url": str(output)}
        tts = AsyncMock(return_value=wav.read_bytes())
        with (
            patch("app.services.creative_studio_video_finishing.settings.RUNWAYML_API_KEY", "test"),
            patch("app.services.creative_studio_video_finishing.settings.RUNWAYML_VOICEOVER_ENABLED", True),
            patch("app.services.creative_studio_video_finishing._ensure_local_video", return_value=self.audible),
            patch("app.services.creative_studio_video_finishing.file_service.save_bytes", side_effect=save),
            patch("app.services.media.voiceover.generate_tts_audio", tts),
        ):
            url, result = await apply_timed_voiceover(
                "fixture.mp4", [(0.5, 1.5, "Hello there.")], tenant_id="test",
            )
        self.assertEqual(result["status"], "done")
        self.assertEqual(tts.call_args.kwargs["script"], "Hello there.")
        self.assertTrue(probe_has_audio(output))
        self.assertAlmostEqual(probe_video_duration(output), 2, delta=0.15)


if __name__ == "__main__":
    unittest.main()
