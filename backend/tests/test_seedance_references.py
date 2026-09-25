"""Identity bindings and rejection behavior; no billable provider calls."""

import unittest
from unittest.mock import AsyncMock, patch

from app.services.media.seedance_references import (
    filter_manifest_for_privacy_retry,
    reference_instructions,
    reference_manifest,
)
from app.services.media.byteplus_seedance_provider import BytePlusSeedanceVideoProvider


class ReferenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.brief = {
            "product_reference_url": "https://example.com/chairs.png",
            "logo_reference_url": "https://example.com/logo.png",
            "reference_assets": [
                {"url": "https://example.com/hero.png", "role": "character"},
                {"url": "https://example.com/kitchen.png", "role": "scene"},
            ],
            "additional_reference_urls": ["https://example.com/hero.png"],
            "storyboard_image_urls": ["https://example.com/chairs.png"],
            "seed_image_role": "first_frame",
        }

    def test_deduplication_keeps_authoritative_roles_and_indices(self):
        manifest = reference_manifest(self.brief, "https://example.com/chairs.png")
        self.assertEqual([asset["role"] for asset in manifest], ["character", "product", "scene", "logo"])
        instructions = reference_instructions(manifest)
        for index, role in enumerate(["CHARACTER", "PRODUCT", "SCENE", "BRAND"], 1):
            self.assertIn(f"Image {index}: {role}", instructions)

    def test_generated_storyboards_cannot_displace_anchors(self):
        self.brief["storyboard_image_urls"] = [f"https://example.com/shot{i}.png" for i in range(12)]
        manifest = reference_manifest(self.brief, "https://example.com/still.png")
        self.assertEqual(len(manifest), 9)
        self.assertEqual([asset["role"] for asset in manifest[:4]], ["character", "product", "scene", "logo"])

    def test_privacy_filter_keeps_product_logo_scene_only(self):
        manifest = reference_manifest(self.brief, "https://example.com/still.png")
        safe = filter_manifest_for_privacy_retry(manifest)
        self.assertEqual([asset["role"] for asset in safe], ["product", "scene", "logo"])

    def test_continuity_frame_is_bound_before_product_and_scene_references(self):
        self.brief["continuity_reference_url"] = "https://example.com/handoff.jpg"
        manifest = reference_manifest(self.brief, None)
        self.assertEqual(
            [asset["role"] for asset in manifest[:5]],
            ["character", "continuity", "product", "scene", "logo"],
        )
        instructions = reference_instructions(manifest)
        self.assertIn("Image 2: CONTINUITY FRAME", instructions)
        self.assertIn("continue forward without replaying", instructions)

    def test_persistent_cast_anchor_precedes_the_latest_continuity_frame(self):
        self.brief.pop("reference_assets")
        self.brief["cast_reference_url"] = "https://example.com/cast.jpg"
        self.brief["continuity_reference_url"] = "https://example.com/handoff.jpg"
        manifest = reference_manifest(self.brief, None)
        self.assertEqual([asset["role"] for asset in manifest[:3]], ["cast", "continuity", "product"])
        instructions = reference_instructions(manifest)
        self.assertIn("Image 1: CAST ANCHOR", instructions)
        self.assertIn("Image 2: CONTINUITY FRAME", instructions)

    def test_too_many_supplied_references_are_not_silently_dropped(self):
        self.brief["additional_reference_urls"] = [f"https://example.com/ref{i}.png" for i in range(7)]
        with self.assertRaisesRegex(ValueError, "at most 9"):
            reference_manifest(self.brief, None)

    async def test_provider_sends_numbered_bindings_in_actual_image_order(self):
        module = "app.services.media.byteplus_seedance_provider"
        submit = AsyncMock(return_value="test-task")
        with (
            patch(module + ".ark_configured", return_value=True),
            patch(module + ".file_url_to_data_uri", side_effect=lambda url: url),
            patch(module + ".create_video_task", submit),
            patch(module + ".poll_video_task", AsyncMock(return_value={"duration": 15})),
            patch(module + ".extract_video_url", return_value="https://example.com/video.mp4"),
            patch(module + "._download_asset", AsyncMock(return_value={"url": "fixture.mp4"})),
            patch("app.services.usage_tracker.record_usage"),
        ):
            result = await BytePlusSeedanceVideoProvider().generate(
                prompt="Six timed shots. Exactly two chairs.", brief=self.brief, copy={},
                format_type="landscape", model="ark-seedance-2-0", tenant_id="test",
                source_image_url="https://example.com/approved-opening.png", duration_seconds=15,
            )
        self.assertEqual(result["status"], "done", result.get("error"))
        request = submit.call_args.kwargs
        self.assertEqual(request["image_data_uri_or_url"], "https://example.com/approved-opening.png")
        self.assertEqual(request["image_role"], "first_frame")
        self.assertIsNone(request["extra_image_refs"])
        self.assertIn("Image 1: APPROVED OPENING FRAME", request["prompt"])
        self.assertNotIn("Image 2:", request["prompt"])

    async def test_privacy_rejection_can_recover_on_anchor_retry(self):
        module = "app.services.media.byteplus_seedance_provider"
        privacy_error = RuntimeError("InputImageSensitiveContentDetected.PrivacyInformation")
        submit = AsyncMock(side_effect=[privacy_error, "anchor-task"])
        with (
            patch(module + ".ark_configured", return_value=True),
            patch(module + ".file_url_to_data_uri", side_effect=lambda url: url),
            patch(module + ".create_video_task", submit),
            patch(module + ".poll_video_task", AsyncMock(return_value={"duration": 15})),
            patch(module + ".extract_video_url", return_value="https://example.com/video.mp4"),
            patch(module + "._download_asset", AsyncMock(return_value={"url": "fixture.mp4"})),
            patch("app.services.usage_tracker.record_usage"),
        ):
            result = await BytePlusSeedanceVideoProvider().generate(
                prompt="Two chairs in a kitchen.", brief=self.brief, copy={},
                format_type="landscape", model="ark-seedance-2-0", tenant_id="test",
            )
        self.assertEqual(result["status"], "done", result.get("error"))
        self.assertEqual(submit.await_count, 2)
        self.assertEqual(result.get("privacy_fallback"), "anchors")
        anchor_request = submit.call_args_list[1].kwargs
        self.assertEqual(
            [ref["url"].split("/")[-1] for ref in anchor_request["extra_image_refs"]],
            ["chairs.png", "kitchen.png", "logo.png"],
        )

    async def test_strict_character_never_falls_back_to_a_replacement_person(self):
        module = "app.services.media.byteplus_seedance_provider"
        privacy_error = RuntimeError("InputImageSensitiveContentDetected.PrivacyInformation")
        submit = AsyncMock(side_effect=privacy_error)
        strict_brief = {**self.brief, "strict_character_reference": True}
        with (
            patch(module + ".ark_configured", return_value=True),
            patch(module + ".file_url_to_data_uri", side_effect=lambda url: url),
            patch(module + ".create_video_task", submit),
            patch("app.services.usage_tracker.record_usage"),
        ):
            result = await BytePlusSeedanceVideoProvider().generate(
                prompt="Keep the selected person in every shot.", brief=strict_brief, copy={},
                format_type="landscape", model="ark-seedance-2-0", tenant_id="test",
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(submit.await_count, 1)
        self.assertIn("selected character reference", result["error"])
        self.assertIn("No replacement person", result["error"])

    async def test_strict_continuity_never_drops_the_previous_chapter_frame(self):
        module = "app.services.media.byteplus_seedance_provider"
        privacy_error = RuntimeError("InputImageSensitiveContentDetected.PrivacyInformation")
        submit = AsyncMock(side_effect=privacy_error)
        strict_brief = {
            **self.brief,
            "continuity_reference_url": "https://example.com/handoff.jpg",
            "strict_continuity_reference": True,
        }
        with (
            patch(module + ".ark_configured", return_value=True),
            patch(module + ".file_url_to_data_uri", side_effect=lambda url: url),
            patch(module + ".create_video_task", submit),
            patch("app.services.usage_tracker.record_usage"),
        ):
            result = await BytePlusSeedanceVideoProvider().generate(
                prompt="Continue the business film.", brief=strict_brief, copy={},
                format_type="landscape", model="ark-seedance-2-0", tenant_id="test",
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(submit.await_count, 1)
        self.assertIn("previous chapter's continuity frame", result["error"])
        self.assertIn("stopped instead of inventing", result["error"])

    async def test_overdue_account_is_reported_as_non_retryable(self):
        module = "app.services.media.byteplus_seedance_provider"
        submit = AsyncMock(side_effect=RuntimeError(
            'BytePlus Seedance create failed (403): {"error":{"code":"AccountOverdueError",'
            '"message":"The request failed because your account has an overdue balance."}}'
        ))
        with (
            patch(module + ".ark_configured", return_value=True),
            patch(module + ".create_video_task", submit),
            patch("app.services.usage_tracker.record_usage"),
        ):
            result = await BytePlusSeedanceVideoProvider().generate(
                prompt="Continue the commercial.", brief={}, copy={},
                format_type="landscape", model="ark-seedance-2-0", tenant_id="test",
                duration_seconds=15,
            )
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["retryable"])
        self.assertEqual(result["error_code"], "AccountOverdueError")
        self.assertIn("Settle/recharge BytePlus billing", result["error"])
        self.assertEqual(submit.await_count, 1)

    async def test_successful_provider_task_is_not_regenerated_when_local_download_fails(self):
        module = "app.services.media.byteplus_seedance_provider"
        submit = AsyncMock(return_value="paid-task")
        with (
            patch(module + ".ark_configured", return_value=True),
            patch(module + ".file_url_to_data_uri", side_effect=lambda url: url),
            patch(module + ".create_video_task", submit),
            patch(module + ".poll_video_task", AsyncMock(return_value={
                "status": "succeeded",
                "duration": 8,
                "usage": {"completion_tokens": 173700, "total_tokens": 173700},
            })),
            patch(module + ".extract_video_url", return_value="https://example.com/paid-video.mp4"),
            patch(module + "._download_asset", AsyncMock(
                side_effect=PermissionError("upload directory denied")
            )),
            patch("app.services.usage_tracker.record_usage"),
        ):
            result = await BytePlusSeedanceVideoProvider().generate(
                prompt="Continue the commercial.", brief={}, copy={},
                format_type="landscape", model="ark-seedance-2-0", tenant_id="test",
                duration_seconds=14,
            )
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["url"], "https://example.com/paid-video.mp4")
        self.assertIn("could not be saved locally", result["download_warning"])
        self.assertEqual(submit.await_count, 1)

    async def test_privacy_rejection_retries_with_safe_anchors_then_text_to_video(self):
        module = "app.services.media.byteplus_seedance_provider"
        privacy_error = RuntimeError("InputImageSensitiveContentDetected.PrivacyInformation")
        submit = AsyncMock(side_effect=[privacy_error, privacy_error, "fallback-task"])
        with (
            patch(module + ".ark_configured", return_value=True),
            patch(module + ".file_url_to_data_uri", side_effect=lambda url: url),
            patch(module + ".create_video_task", submit),
            patch(module + ".poll_video_task", AsyncMock(return_value={"duration": 15})),
            patch(module + ".extract_video_url", return_value="https://example.com/video.mp4"),
            patch(module + "._download_asset", AsyncMock(return_value={"url": "fixture.mp4"})),
            patch("app.services.usage_tracker.record_usage"),
        ):
            result = await BytePlusSeedanceVideoProvider().generate(
                prompt="Two chairs in a kitchen.", brief=self.brief, copy={},
                format_type="landscape", model="ark-seedance-2-0", tenant_id="test",
            )
        self.assertEqual(result["status"], "done", result.get("error"))
        self.assertEqual(submit.await_count, 3)
        self.assertEqual(result.get("privacy_fallback"), "text_to_video")
        self.assertIn("text-to-video", result.get("duration_warning", ""))
        final_request = submit.call_args.kwargs
        self.assertIsNone(final_request["image_data_uri_or_url"])
        self.assertIsNone(final_request["extra_image_refs"])


if __name__ == "__main__":
    unittest.main()
