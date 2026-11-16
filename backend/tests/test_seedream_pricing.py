from types import SimpleNamespace

from app.services import usage_pricing
from app.services.usage_tracker import effective_cost_usd, estimate_media_cost


def setup_function():
    usage_pricing.set_overrides({})


def test_seedream_tiers_are_priced():
    for model, expected in [
        ("seedream-5-0-260128", 0.035),
        ("ark-seedream-5-0-lite", 0.035),
        ("dola-seedream-5-0-pro-260628", 0.05),
        ("dola-seedream-5-0-flash-260915", 0.02),
    ]:
        cost, credits = estimate_media_cost(provider="byteplus", model=model)
        assert cost == expected
        assert credits > 0


def test_admin_override_wins():
    usage_pricing.set_overrides({"image_usd_each": {"seedream-5-0-pro": 0.08}})
    cost, _ = estimate_media_cost(provider="byteplus", model="ark-seedream-5-0-pro")
    assert cost == 0.08


def test_seedance_video_is_unchanged():
    cost, credits = estimate_media_cost(provider="byteplus", model="dreamina-seedance-2-5-260628")
    assert (cost, credits) == (0.0, 0.0)


def test_old_zero_cost_rows_are_repriced_only_when_successful():
    ok = SimpleNamespace(provider="byteplus", model="seedream-5-0-260128", operation="creative_studio_image",
                         cost_usd=0, success=True, extra={})
    bad = SimpleNamespace(provider="byteplus", model="seedream-5-0-260128", operation="creative_studio_image",
                          cost_usd=0, success=False, extra={})
    assert effective_cost_usd(ok) == 0.035
    assert effective_cost_usd(bad) == 0.0
