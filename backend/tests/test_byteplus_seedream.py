import unittest

from app.services.creative_studio_production_memory import (
    approved_broll_seedance_urls,
    approved_broll_urls,
)
from app.services.media.byteplus_seedance_client import seedance_reference_data_uri
from app.services.media.byteplus_seedream_client import (
    is_byteplus_ark_media_url,
    is_byteplus_seedream_model,
    map_format_to_size,
    resolve_seedream_api_model,
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


if __name__ == "__main__":
    unittest.main()
