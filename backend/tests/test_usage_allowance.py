import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services.usage_allowance import require_usage_allowance, reset_allowance


def _user(role="member"):
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        email="user@example.com",
        full_name="Test User",
        role=role,
    )


def test_admin_is_exempt_without_usage_query():
    user = _user("admin")
    assert asyncio.run(require_usage_allowance(current_user=user, db=object())) is user


def test_member_is_not_blocked_while_enforcement_is_disabled():
    user = _user()
    snapshot = {"limit_reached": True, "limit_usd": 30.0, "period_spend_usd": 30.25}
    with patch("app.services.usage_allowance.allowance_status", new=AsyncMock(return_value=snapshot)):
        assert asyncio.run(require_usage_allowance(current_user=user, db=object())) is user


def test_reset_starts_new_period_and_preserves_previous_period_amount():
    target = _user()
    admin = _user("admin")
    db = SimpleNamespace(add=lambda row: setattr(db, "added", row), flush=AsyncMock())
    before = {"period_spend_usd": 31.5}
    after = {"period_spend_usd": 0.0, "remaining_usd": 30.0, "reset_count": 1}
    with patch(
        "app.services.usage_allowance.allowance_status",
        new=AsyncMock(side_effect=[before, after]),
    ):
        result = asyncio.run(
            reset_allowance(db, target_user=target, reset_by=admin, note="Management approved")
        )
    assert float(db.added.previous_period_spend_usd) == 31.5
    assert db.added.note == "Management approved"
    assert result["remaining_usd"] == 30.0
