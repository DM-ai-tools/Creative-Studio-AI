import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services.creative_studio_production_memory import (
    approved_broll_seedance_urls,
    approved_broll_urls,
)
from app.services.media.byteplus_seedance_client import seedance_reference_data_uri
from app.services.media.byteplus_seedream_client import (
    generate_seedream_image,
    is_byteplus_ark_media_url,
    is_byteplus_seedream_model,
    map_format_to_size,
    resolve_seedream_api_model,
)
from app.services.media.byteplus_seedream_catalog import (
    creative_studio_still_model_options,
)
from app.services.media.registry import get_image_provider


class BytePlusSeedreamTests(unittest.TestCase):
    def test_model_detection_and_resolution(self):
        self.assertTrue(is_byteplus_seedream_model("ark-seedream-5-0-lite"))
        self.assertTrue(is_byteplus_seedream_model("ark-seedream-5-0-pro"))
        self.assertFalse(is_byteplus_seedream_model("openai-gpt-image-2"))
        self.assertEqual(
            resolve_seedream_api_model("ark-seedream-5-0-pro"),
            "dola-seedream-5-0-pro-260628",
        )
        self.assertEqual(
            resolve_seedream_api_model("ark-seedream-5-0-flash"),
            "dola-seedream-5-0-flash-260915",
        )

    def test_byteplus_tos_url_detection(self):
        url = (
            "https://ark-acg-ap-southeast-1.tos-ap-southeast-1.volces.com/"
            "seedream/example.png?sig=abc"
        )
        self.assertTrue(is_byteplus_ark_media_url(url))
        self.assertFalse(is_byteplus_ark_media_url("/files/local.png"))

    def test_seedance_reference_passthrough(self):
        url = (
            "https://ark-acg-ap-southeast-1.tos-ap-southeast-1.volces.com/"
            "seedream/example.png"
        )
        self.assertEqual(seedance_reference_data_uri(url), url)

    def test_format_to_size(self):
        self.assertEqual(map_format_to_size("reel", "9/16"), "1024x1536")
        self.assertEqual(map_format_to_size("carousel", "16/9"), "1536x1024")

    def test_registry_routes_seedream(self):
        provider = get_image_provider("ark-seedream-5-0-lite")
        self.assertEqual(provider.provider_id, "byteplus")

    def test_creative_studio_still_catalog_includes_gpt2_and_seedream_flash(self):
        still = creative_studio_still_model_options()
        ids = {o.id for o in still}
        self.assertIn("openai-gpt-image-2.6-sunburst", ids)
        self.assertIn("ark-seedream-5-0-flash", ids)
        flash = next(o for o in still if o.id == "ark-seedream-5-0-flash")
        self.assertIn("dola-seedream-5-0-flash", flash.provider_model)

    def test_approved_broll_seedance_url_prefers_byteplus(self):
        memory: dict = {
            "approved_broll": {
                "1": {
                    "index": 1,
                    "url": "/files/local.png",
                    "byteplus_url": (
                        "https://ark-acg-ap-southeast-1.tos-ap-southeast-1.volces.com/x.png"
                    ),
                }
            }
        }
        self.assertEqual(approved_broll_urls(memory)[1], "/files/local.png")
        self.assertIn(
            "ark-acg-ap-southeast-1.tos-ap-southeast-1.volces.com",
            approved_broll_seedance_urls(memory)[1],
        )


class _FakeImageResponse:
    status_code = 200
    content = b"{}"
    text = ""

    def json(self):
        return {
            "data": [
                {
                    "url": (
                        "https://ark-acg-ap-southeast-1.tos-ap-southeast-1.volces.com/"
                        "seedream/same-account.png"
                    )
                }
            ]
        }


class _FakeImageClient:
    def __init__(self):
        self.headers = None

    async def post(self, _url, *, json, headers, timeout):
        _ = (json, timeout)
        self.headers = headers
        return _FakeImageResponse()


class BytePlusSeedreamCredentialTests(unittest.IsolatedAsyncioTestCase):
    async def test_seedream_uses_selected_seedance_25_key(self):
        client = _FakeImageClient()
        with (
            patch.object(settings, "ARK_API_KEY", "seedance-20-key"),
            patch.object(settings, "ARK_API_KEY_25", "seedance-25-key"),
        ):
            await generate_seedream_image(
                client,
                prompt="fictional presenter",
                model="dola-seedream-5-0-pro-260628",
                target_video_model="ark-seedance-2-5",
            )
        self.assertEqual(client.headers["Authorization"], "Bearer seedance-25-key")


if __name__ == "__main__":
    unittest.main()
