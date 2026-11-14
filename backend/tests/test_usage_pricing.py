"""Admin-editable pricing and resolution-aware Seedance cost estimates."""

from types import SimpleNamespace

import pytest

from app.services import usage_pricing as pricing
from app.services.usage_tracker import (
    effective_cost_usd,
    estimate_llm_cost,
    infer_seedance_resolution,
    manager_report_seedance_cost_usd,
    seedance_cost_detail,
)


@pytest.fixture(autouse=True)
def _reset_overrides():
    pricing.set_overrides({})
    yield
    pricing.set_overrides({})


def _row(**kwargs):
    defaults = {
        "provider": "byteplus",
        "model": "dreamina-seedance-2-5-260628",
        "operation": "video_generation",
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0,
        "success": True,
        "extra": {},
        "tenant_id": None,
        "created_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_infer_resolution_from_tokens_per_second():
    assert infer_seedance_resolution(288_400, 30) == "480p"
    assert infer_seedance_resolution(648_000, 30) == "720p"
    assert infer_seedance_resolution(1_462_188, 30) == "1080p"
    assert infer_seedance_resolution(0, 30) is None
    assert infer_seedance_resolution(100, 0) is None


def test_legacy_480p_clip_is_not_priced_as_1080p():
    # 288.4k tokens over 30s is a 480p clip. It used to be priced at the 1080p rate.
    row = _row(completion_tokens=288_400, total_tokens=288_400, extra={"duration_seconds": 30})
    detail = seedance_cost_detail(row)
    assert detail["resolution"] == "480p"
    assert detail["resolution_inferred"] is True
    assert detail["low"] == round(288_400 / 1_000_000 * 6.40, 4)
    assert detail["high"] == round(288_400 / 1_000_000 * 10.70, 4)
    assert detail["mid"] == detail["high"]  # unknown video input -> no-video rate


def test_explicit_resolution_wins_over_inference():
    row = _row(
        completion_tokens=288_400,
        total_tokens=288_400,
        extra={"duration_seconds": 30, "resolution": "1080p", "with_video_input": False},
    )
    detail = seedance_cost_detail(row)
    assert detail["resolution"] == "1080p"
    assert detail["resolution_inferred"] is False
    assert detail["mid"] == round(288_400 / 1_000_000 * 11.70, 4)


def test_reference_video_clips_do_not_guess_resolution_from_tokens():
    # Tokens include the input clip, so tokens/sec would over-state resolution.
    row = _row(
        completion_tokens=600_000,
        total_tokens=600_000,
        extra={"duration_seconds": 15, "with_video_input": True},
    )
    detail = seedance_cost_detail(row)
    assert detail["resolution_inferred"] is False
    assert detail["resolution"] == "1080p"  # default for Seedance 2.5 when unknown
    assert detail["mid"] == round(600_000 / 1_000_000 * 7.0, 4)  # with-video 1080p rate


def test_no_info_uses_1080p_no_video_rate_for_seedance_25():
    row = _row(completion_tokens=1_000_000, total_tokens=1_000_000)
    assert effective_cost_usd(row) == 11.7


def test_admin_override_changes_seedance_cost():
    row = _row(
        completion_tokens=1_000_000,
        total_tokens=1_000_000,
        extra={"resolution": "720p", "with_video_input": False},
    )
    assert effective_cost_usd(row) == 10.70
    pricing.set_overrides({"seedance_per_m_tokens": {"2.5": {"720p": {"no_video": 5.0}}}})
    assert effective_cost_usd(row) == 5.0
    # The untouched cell keeps its default.
    assert pricing.seedance_rate("dreamina-seedance-2-5-260628", "720p", with_video=True) == 6.40


def test_admin_override_changes_llm_cost_and_default():
    assert estimate_llm_cost("anthropic/claude-haiku-4.5", 1_000_000, 1_000_000) == 6.0
    pricing.set_overrides(
        {
            "llm_per_m_tokens": {"anthropic/claude-haiku-4.5": {"input": 2.0, "output": 10.0}},
            "llm_default_per_m_tokens": {"input": 1.0, "output": 1.0},
        }
    )
    assert estimate_llm_cost("anthropic/claude-haiku-4.5", 1_000_000, 1_000_000) == 12.0
    assert estimate_llm_cost("some/unknown-model", 1_000_000, 1_000_000) == 2.0


def test_manager_report_matches_dashboard_cost():
    row = _row(completion_tokens=288_400, total_tokens=288_400, extra={"duration_seconds": 30})
    assert manager_report_seedance_cost_usd(row) == effective_cost_usd(row)


def test_failed_seedance_row_costs_nothing():
    row = _row(success=False, error="TimeoutError", completion_tokens=0)
    assert effective_cost_usd(row) == 0.0


def test_validate_overrides_accepts_good_and_rejects_bad_input():
    clean = pricing.validate_overrides(
        {
            "seedance_per_m_tokens": {"2.5": {"480p": {"no_video": "9.5"}}},
            "llm_per_m_tokens": {" Foo/Bar ": {"input": 1, "output": 2}},
            "image_usd_each": {"gpt-image-2": 0.06},
        }
    )
    assert clean["seedance_per_m_tokens"]["2.5"]["480p"]["no_video"] == 9.5
    assert "foo/bar" in clean["llm_per_m_tokens"]
    assert clean["image_usd_each"]["gpt-image-2"] == 0.06

    for bad in (
        {"seedance_per_m_tokens": {"9.9": {"720p": {"no_video": 1}}}},
        {"seedance_per_m_tokens": {"2.5": {"8k": {"no_video": 1}}}},
        {"seedance_per_m_tokens": {"2.5": {"720p": {"no_video": -1}}}},
        {"seedance_per_m_tokens": {"2.5": {"720p": {"no_video": "abc"}}}},
        {"seedance_fallback_usd_per_30s": 10**9},
        {"llm_default_per_m_tokens": "free"},
    ):
        with pytest.raises(pricing.PricingValidationError):
            pricing.validate_overrides(bad)


# ── official BytePlus rates, per model ───────────────────────────────────────


@pytest.mark.parametrize(
    "model,res,with_video,expected",
    [
        ("dreamina-seedance-2-5-260628", "720p", False, 10.70),
        ("dreamina-seedance-2-5-260628", "480p", False, 10.70),
        ("dreamina-seedance-2-5-260628", "1080p", False, 11.70),
        ("dreamina-seedance-2-5-260628", "720p", True, 6.40),
        ("dreamina-seedance-2-5-260628", "1080p", True, 7.00),
        ("dreamina-seedance-2-0-260128", "720p", False, 7.0),
        ("dreamina-seedance-2-0-260128", "1080p", False, 7.7),
        ("dreamina-seedance-2-0-260128", "720p", True, 4.3),
        ("dreamina-seedance-2-0-260128", "1080p", True, 4.7),
        ("dreamina-seedance-2-0-fast-260128", "720p", False, 5.6),
        ("dreamina-seedance-2-0-mini-260615", "720p", False, 3.5),
        ("dreamina-seedance-2-5-flash-261115", "720p", False, 7.0),
        ("seedance-1-0-pro-250528", "720p", False, 2.5),
    ],
)
def test_default_rates_match_official_byteplus_table(model, res, with_video, expected):
    assert pricing.seedance_rate(model, res, with_video=with_video) == expected


def test_seedance_20_clip_uses_20_rates_not_25():
    # This clip used to be priced with the 2.5 rate ($10.70) instead of $7.00.
    row = _row(
        model="dreamina-seedance-2-0-260128",
        completion_tokens=100_900,
        total_tokens=100_900,
        extra={"resolution": "720p", "with_video_input": False},
    )
    assert effective_cost_usd(row) == round(100_900 / 1_000_000 * 7.0, 4)


def test_formula_matches_documented_per_second_prices():
    # BytePlus docs: Seedance 2.0 is about $0.07/s at 480p and $0.37/s at 1080p (24 fps, 16:9).
    per_second_480 = 864 * 496 * 24 / 1024
    per_second_1080 = 1920 * 1080 * 24 / 1024
    assert round(per_second_480 / 1_000_000 * 7.0, 2) == 0.07
    assert round(per_second_1080 / 1_000_000 * 7.7, 2) == 0.37
    assert infer_seedance_resolution(int(per_second_480 * 10), 10) == "480p"
    assert infer_seedance_resolution(int(per_second_1080 * 10), 10) == "1080p"


# ── 4K (2160p): only Seedance 2.0 supports it, at a lower per-token rate ─────


def test_seedance_20_4k_rates_match_official_table_and_per_second_price():
    assert pricing.seedance_rate("dreamina-seedance-2-0-260128", "2160p", with_video=False) == 4.0
    assert pricing.seedance_rate("dreamina-seedance-2-0-260128", "2160p", with_video=True) == 2.4
    per_second_4k = 3840 * 2160 * 24 / 1024
    # BytePlus docs: Seedance 2.0 4K is about $0.78 per second.
    assert round(per_second_4k / 1_000_000 * 4.0, 2) == 0.78
    assert infer_seedance_resolution(int(per_second_4k * 10), 10) == "2160p"


def test_models_without_4k_repeat_their_1080p_rate():
    assert pricing.seedance_rate("dreamina-seedance-2-5-260628", "2160p", with_video=False) == 11.7


def test_4k_clip_is_priced_with_the_4k_rate():
    row = _row(
        model="dreamina-seedance-2-0-260128",
        completion_tokens=1_944_000,
        total_tokens=1_944_000,
        extra={"duration_seconds": 10, "with_video_input": False},
    )
    detail = seedance_cost_detail(row)
    assert detail["resolution"] == "2160p"
    assert detail["mid"] == round(1_944_000 / 1_000_000 * 4.0, 4)
