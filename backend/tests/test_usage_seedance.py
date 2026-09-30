"""Seedance cost estimation for the usage dashboard."""

from types import SimpleNamespace

from app.services.usage_tracker import (
    _build_seedance_summary,
    effective_cost_usd,
    estimate_byteplus_seedance_cost_usd,
    is_byteplus_seedance_row,
)


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


def test_estimate_byteplus_seedance_cost_range():
    est = estimate_byteplus_seedance_cost_usd(1_462_188)
    assert est["low"] == 9.358
    assert est["high"] == 15.6454
    assert est["mid"] == round((est["low"] + est["high"]) / 2, 4)


def test_is_byteplus_seedance_row():
    assert is_byteplus_seedance_row(_row())
    assert not is_byteplus_seedance_row(_row(provider="openrouter", operation="llm", model="gpt-4o"))


def test_effective_cost_usd_uses_estimate_when_provider_cost_missing():
    row = _row(completion_tokens=1_000_000, total_tokens=1_000_000)
    assert effective_cost_usd(row) == 8.55


def test_effective_cost_usd_prefers_stored_cost():
    row = _row(completion_tokens=1_000_000, cost_usd=12.34)
    assert effective_cost_usd(row) == 12.34


def test_build_seedance_summary():
    rows = [
        _row(
            id="a",
            completion_tokens=1_462_188,
            total_tokens=1_462_188,
            extra={"task_id": "cgt-test-1"},
        ),
        _row(
            id="b",
            success=False,
            error="AccountOverdueError",
        ),
    ]
    summary = _build_seedance_summary(rows, tenant_names={})
    assert summary["successful_clips"] == 1
    assert summary["failed_calls"] == 1
    assert summary["total_tokens"] == 1_462_188
    assert summary["recent_clips"][0]["task_id"] == "cgt-test-1"
    assert summary["cost_usd_low"] > 0
    assert summary["cost_usd_high"] >= summary["cost_usd_low"]
