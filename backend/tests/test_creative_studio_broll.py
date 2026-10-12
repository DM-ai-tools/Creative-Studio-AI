import unittest

from app.services.creative_studio_broll import (
    build_chapter_broll_segments,
    parse_broll_images,
)
from app.services.creative_studio_chat_service import ACTIONS


SAMPLE = """
IMAGE 1 - PROFITABLE SALES VS SPEND
Scene timing:
0:08-0:09.5
Image generation prompt:
Create a premium dashboard with legible labels: WASTED SPEND, PROFIT DRIVERS, and sharp bar charts.

IMAGE 2 - PROFIT DRIVERS
Scene timing:
0:09.5-0:11
Image generation prompt:
Create campaign paths flowing toward stronger conversion blocks.

IMAGE 3 - WASTED SPEND
Scene timing:
0:20-0:22.5
Image generation prompt:
Strategist analysing inefficient budget blocks on a monitor.
"""


class BrollPlanTests(unittest.TestCase):
    def test_broll_batch_actions_registered(self):
        self.assertIn("generate_all_broll", ACTIONS)
        self.assertIn("regenerate_broll_image", ACTIONS)
        self.assertIn("approve_all_broll", ACTIONS)

    def test_parse_broll_images_reads_image_blocks(self):
        items = parse_broll_images(SAMPLE)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["index"], 1)
        self.assertAlmostEqual(items[0]["start"], 8.0)
        self.assertIn("dashboard", items[0]["image_prompt"].lower())
        self.assertTrue(items[0]["wants_readable_text"])

    def test_parse_generated_background_image_blocks(self):
        brief = """
9. GENERATED BACKGROUND IMAGE 1

NAME:
CAMPAIGN BUDGET VS SALES CLARITY

USE DURING:
Approximately 0:07-0:11

IMAGE GENERATION PROMPT:
Create abstract campaign budget bars. No readable generated words.

VIDEO MOTION:
Gentle horizontal parallax.

11. GENERATED BACKGROUND IMAGE 2

NAME:
AUDIT PRIORITIES AND 90-DAY ROADMAP

USE DURING:
Approximately 0:18-0:27

IMAGE GENERATION PROMPT:
Create an abstract four-stage roadmap. No readable words or labels.

VIDEO MOTION:
Slow left-to-right flow.
"""
        items = parse_broll_images(brief)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "CAMPAIGN BUDGET VS SALES CLARITY")
        self.assertEqual((items[0]["start"], items[0]["end"]), (7.0, 11.0))
        self.assertFalse(items[0]["wants_readable_text"])
        self.assertEqual(items[1]["title"], "AUDIT PRIORITIES AND 90-DAY ROADMAP")
        self.assertEqual((items[1]["start"], items[1]["end"]), (18.0, 27.0))

    def test_global_blur_rule_does_not_disable_readable_broll(self):
        brief = SAMPLE + "\nGLOBAL RULE: blur all dashboard text and keep UI unreadable."
        items = parse_broll_images(brief)
        self.assertTrue(items[0]["wants_readable_text"])

    def test_abstract_broll_when_image_prompt_requests_blur(self):
        brief = SAMPLE.replace(
            "legible labels:",
            "blurred unreadable abstract UI only — no readable words.",
        )
        items = parse_broll_images(brief)
        self.assertFalse(items[0]["wants_readable_text"])
        self.assertIn("soft-blurred", items[0]["image_prompt"].lower())

    def test_readable_motion_prompt_preserves_text(self):
        from app.services.creative_studio_broll import broll_motion_prompt

        motion = broll_motion_prompt(
            title="Dashboard", duration=2.0, kind="broll", preserve_text=True,
        )
        self.assertIn("Preserve every existing letter", motion)

    def test_build_chapter_segments_uses_approved_broll(self):
        plan = parse_broll_images(SAMPLE)
        segments = build_chapter_broll_segments(
            chapter_index=0,
            chapter_start=0.0,
            chapter_end=15.0,
            opening_still_url="https://example.com/presenter.png",
            proof_still_url="https://example.com/stat.png",
            broll_plan=plan,
            approved_broll={
                1: "https://example.com/broll1.png",
                2: "https://example.com/broll2.png",
            },
            chapter_motion_prompt="Presenter hook chapter.",
        )
        kinds = [seg["kind"] for seg in segments]
        self.assertIn("broll", kinds)
        self.assertIn("presenter", kinds)
        self.assertTrue(
            any(
                str(seg.get("first_frame_url") or "").endswith("broll1.png")
                for seg in segments
            )
        )
        presenter = [seg for seg in segments if seg["kind"] == "presenter"]
        self.assertTrue(presenter)
        self.assertTrue(all(seg.get("text_to_video") for seg in presenter))
        self.assertTrue(all(not seg.get("first_frame_url") for seg in presenter))

    def test_presenter_call_cannot_preview_or_duplicate_broll(self):
        plan = parse_broll_images(SAMPLE)
        chapter_prompt = """
PRESENTER IDENTITY LOCK
Australian female strategist, age 30-34, charcoal blazer, white blouse.
Premium modern office, confident direct-to-camera delivery.

CHAPTER 1 — 00:00-00:15
00:00-00:08 presenter hook.
00:08-00:09.5 IMAGE 1 — SPEND VERSUS PROFIT.
00:09.5-00:11 IMAGE 2 — PROFIT DRIVERS.
00:11-00:15 uploaded PROOF dashboard.
"""
        segments = build_chapter_broll_segments(
            chapter_index=0,
            chapter_start=0.0,
            chapter_end=15.0,
            opening_still_url="",
            proof_still_url="https://example.com/stat.png",
            broll_plan=plan,
            approved_broll={
                1: "https://example.com/broll1.png",
                2: "https://example.com/broll2.png",
            },
            chapter_motion_prompt=chapter_prompt,
        )
        presenter = next(seg for seg in segments if seg["kind"] == "presenter")
        prompt = str(presenter["prompt"])
        self.assertIn("PRESENTER-ONLY SEGMENT", prompt)
        self.assertIn("Australian female strategist", prompt)
        self.assertNotIn("SPEND VERSUS PROFIT", prompt)
        self.assertNotIn("PROFIT DRIVERS", prompt)
        self.assertNotIn("uploaded PROOF dashboard", prompt)
        self.assertEqual(
            sum(
                1
                for seg in segments
                if str(seg.get("first_frame_url") or "").endswith("broll1.png")
            ),
            1,
        )
        self.assertEqual(
            sum(
                1
                for seg in segments
                if str(seg.get("first_frame_url") or "").endswith("broll2.png")
            ),
            1,
        )

    def test_chapter_two_first_presenter_requests_continuity(self):
        plan = parse_broll_images(SAMPLE)
        segments = build_chapter_broll_segments(
            chapter_index=1,
            chapter_start=15.0,
            chapter_end=30.0,
            opening_still_url="",
            proof_still_url="https://example.com/stat.png",
            broll_plan=plan,
            approved_broll={3: "https://example.com/broll3.png"},
            chapter_motion_prompt="Clip 2 body.",
        )
        presenters = [seg for seg in segments if seg["kind"] == "presenter"]
        self.assertTrue(presenters)
        self.assertTrue(presenters[0].get("use_continuity"))

    def test_product_only_chapter_never_generates_a_presenter(self):
        plan = parse_broll_images(SAMPLE)
        segments = build_chapter_broll_segments(
            chapter_index=0,
            chapter_start=0.0,
            chapter_end=15.0,
            opening_still_url="https://example.com/product.png",
            proof_still_url=None,
            broll_plan=plan,
            approved_broll={
                1: "https://example.com/broll1.png",
                2: "https://example.com/broll2.png",
            },
            chapter_motion_prompt=(
                "PRODUCT-ONLY VIDEO. PRESENTER: NONE. Show the uploaded product "
                "and approved scenes only."
            ),
        )
        self.assertTrue(segments)
        self.assertNotIn("presenter", [seg["kind"] for seg in segments])
        self.assertTrue(all(seg.get("first_frame_url") for seg in segments))
        self.assertTrue(all(not seg.get("text_to_video") for seg in segments))
        self.assertTrue(
            all(
                "presenter, spokesperson" in str(seg.get("prompt") or "").lower()
                for seg in segments
                if seg["kind"] == "product"
            )
        )

    def test_no_presenter_still_does_not_activate_product_only_mode(self):
        from app.services.creative_studio_broll import brief_requests_product_only

        self.assertTrue(
            brief_requests_product_only("VIDEO MODE: PRODUCT-ONLY\nPRESENTER: NONE")
        )
        self.assertFalse(
            brief_requests_product_only(
                "No presenter still. Seedance must generate the presenter and keep her consistent."
            )
        )
        self.assertFalse(
            brief_requests_product_only(
                """
DO NOT GENERATE A PRESENTER IMAGE WITH GPT IMAGE 2.
The presenter must be generated directly inside Seedance.
IMAGE 1 - SPEND VERSUS PROFIT
Image generation prompt:
Create a dashboard scene. No presenter. No visible speaking person.
"""
            )
        )

    def test_openai_credit_failure_is_actionable_and_non_retryable(self):
        from app.services.creative_studio_job_service import _terminal_broll_provider_error

        message = _terminal_broll_provider_error(
            "OpenAI Images API 429: credit_balance_exhausted; no credits remaining"
        )
        self.assertIn("credit balance is exhausted", str(message))
        self.assertIn("No Seedance video request was sent", str(message))
        self.assertIsNone(_terminal_broll_provider_error("temporary upstream timeout"))

    def test_post_production_clock_overlay_section_is_parsed(self):
        from app.services.creative_studio_video_finishing import extract_overlay_events

        brief = """
POST-PRODUCTION TEXT AND CTA

Do not generate these captions inside Seedance.

00:00–00:04

SPENDING $5K+ ON GOOGLE ADS?

00:15–00:20

$5.33M GOOGLE ADS SPEND
$26.5M E-COMMERCE REVENUE

00:27–00:30

BOOK YOUR STRATEGY CALL
trafficradius.com.au

MUSIC
Use one restrained instrumental track.
"""
        self.assertEqual(
            extract_overlay_events(brief),
            [
                (0.0, 4.0, "SPENDING $5K+ ON GOOGLE ADS?"),
                (15.0, 20.0, r"$5.33M GOOGLE ADS SPEND\N$26.5M E-COMMERCE REVENUE"),
                (27.0, 30.0, r"BOOK YOUR STRATEGY CALL\Ntrafficradius.com.au"),
            ],
        )

    def test_chapter_voiceover_is_distributed_inside_each_chapter(self):
        from app.services.creative_studio_video_finishing import extract_voiceover_events

        brief = """
CHAPTER 1 — 00:00–00:15
00:00–00:08 — PRESENTER
VOICEOVER:
“Opening sentence stays in chapter one.”
00:11–00:15 — PROOF
VOICEOVER:
“Second chapter-one sentence.”

CHAPTER 2 — 00:15–00:30
00:15–00:20 — PROOF AND PRESENTER
VOICEOVER:
“Proof sentence stays in chapter two.”
00:24–00:27 — PLAN
VOICEOVER:
“Audit sentence.”
00:27–00:30 — CTA
VOICEOVER:
“Book today.”
"""
        events = extract_voiceover_events(brief, duration_seconds=30)
        chapter_one = [event for event in events if event[0] < 15]
        chapter_two = [event for event in events if event[0] >= 15]
        self.assertEqual(len(chapter_one), 2)
        self.assertEqual(len(chapter_two), 3)
        self.assertTrue(all(end <= 15 for _, end, _ in chapter_one))
        self.assertTrue(all(start >= 15 and end <= 30 for start, end, _ in chapter_two))

    def test_global_events_are_rebased_for_second_chapter(self):
        from app.services.creative_studio_job_service import (
            _chapter_timeline_window,
            _localize_timed_events,
        )

        data = {"film_chapter_index": 1, "full_film_duration": 30}
        memory = {"shot_list": [
            {"chapter": 1, "start": 0.0, "end": 15.0},
            {"chapter": 2, "start": 15.0, "end": 30.0},
        ]}
        start, end = _chapter_timeline_window(data, memory, generate_duration=15)
        self.assertEqual((start, end), (15.0, 30.0))
        self.assertEqual(
            _localize_timed_events(
                [(0, 4, "wrong chapter"), (15, 20, "proof"), (23, 27, "audit"), (27, 30, "cta")],
                start=start,
                end=end,
            ),
            [(0.0, 5.0, "proof"), (8.0, 12.0, "audit"), (12.0, 15.0, "cta")],
        )

    def test_video_job_result_payload_keeps_chapter_handoff_fields(self):
        from app.services.creative_studio_job_service import _video_job_result_payload

        payload = _video_job_result_payload(
            result={
                "url": "https://example.com/ch1.mp4",
                "partial": True,
                "next_chapter_image_available": True,
                "completed_segments": 1,
                "segment_count": 2,
                "continuity_reference_url": "https://example.com/frame.png",
                "chapter_index": 1,
                "note": "Chapter 1/2 is ready.",
            },
            model="seedance",
            seed_url=None,
            generate_duration=15,
            requested_duration=30,
            stitch_note="technical stitch note",
            credits=None,
            out_warn=None,
        )
        self.assertTrue(payload["next_chapter_image_available"])
        self.assertEqual(payload["completed_segments"], 1)
        self.assertEqual(payload["continuity_reference_url"], "https://example.com/frame.png")
        self.assertEqual(payload["note"], "Chapter 1/2 is ready.")
