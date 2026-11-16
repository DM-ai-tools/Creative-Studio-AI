from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.services.usage_export_service import parse_usage_date_range
from app.services.usage_tracker import _build_daily_series


def _row(day: str, cost: float):
    return SimpleNamespace(
        created_at=datetime.fromisoformat(f"{day}T12:00:00+00:00"),
        model="m", provider="p", cost_usd=cost,
    )


def test_daily_series_ends_on_the_custom_end_date_not_today():
    rows = [_row("2026-03-02", 5.0), _row("2026-03-04", 7.0)]
    series, _ = _build_daily_series(
        rows, value_fn=lambda r: r.cost_usd, days=5, end_date=date(2026, 3, 5)
    )
    assert [p["date"] for p in series] == [
        "2026-03-01", "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05",
    ]
    assert [p["total"] for p in series] == [0.0, 5.0, 0.0, 7.0, 0.0]


def test_custom_range_covers_whole_days_and_rejects_bad_input():
    since, until, _ = parse_usage_date_range(date_from=date(2026, 3, 2), date_to=date(2026, 3, 2))
    assert since == datetime(2026, 3, 2, tzinfo=timezone.utc)
    assert until.date() == date(2026, 3, 2) and until.hour == 23
    try:
        parse_usage_date_range(date_from=date(2026, 3, 5), date_to=date(2026, 3, 1))
    except ValueError:
        pass
    else:
        raise AssertionError("end before start must be rejected")
