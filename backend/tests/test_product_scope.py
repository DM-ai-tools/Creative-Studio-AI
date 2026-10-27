import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.core.product_scope import (
    PRODUCT_SCOPE_CREATIVE_STUDIO_SEEDANCE25,
    coerce_creative_studio_video_model,
    filter_video_catalog_for_user,
    is_creative_studio_seedance25_only,
    require_full_studio_access,
)
def _user(scope: str | None = None):
    u = MagicMock()
    u.product_scope = scope
    return u


class ProductScopeTests(unittest.TestCase):
    def test_scope_detection(self):
        self.assertFalse(is_creative_studio_seedance25_only(_user(None)))
        self.assertTrue(
            is_creative_studio_seedance25_only(_user(PRODUCT_SCOPE_CREATIVE_STUDIO_SEEDANCE25))
        )

    def test_full_studio_blocked_for_cs25(self):
        with self.assertRaises(HTTPException) as ctx:
            require_full_studio_access(_user(PRODUCT_SCOPE_CREATIVE_STUDIO_SEEDANCE25))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_video_model_coercion(self):
        scoped = _user(PRODUCT_SCOPE_CREATIVE_STUDIO_SEEDANCE25)
        self.assertEqual(
            coerce_creative_studio_video_model(scoped, "ark-seedance-2-5"),
            "ark-seedance-2-5",
        )
        with self.assertRaises(HTTPException):
            coerce_creative_studio_video_model(scoped, "ark-seedance-2-0")

    def test_filter_video_catalog(self):
        scoped = _user(PRODUCT_SCOPE_CREATIVE_STUDIO_SEEDANCE25)
        opts = [
            {"id": "ark-seedance-2-0", "label": "2.0"},
            {"id": "ark-seedance-2-5", "label": "2.5"},
        ]
        filtered = filter_video_catalog_for_user(scoped, opts)
        self.assertEqual([o["id"] for o in filtered], ["ark-seedance-2-5"])


if __name__ == "__main__":
    unittest.main()
