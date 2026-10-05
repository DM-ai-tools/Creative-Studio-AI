from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.seedance_health import check_seedance_credits


@pytest.mark.asyncio
async def test_check_seedance_not_configured():
    with patch("app.services.seedance_health.ark_configured", return_value=False):
        result = await check_seedance_credits()
    assert result["configured"] is False
    assert result["status"] == "not_configured"


@pytest.mark.asyncio
async def test_check_seedance_billing_ok():
    list_response = httpx.Response(
        200,
        json={
            "total": 3,
            "items": [
                {"status": "succeeded"},
                {"status": "failed", "error": "privacy filter"},
            ],
        },
        request=httpx.Request("GET", "https://example.test/tasks"),
    )
    create_response = httpx.Response(
        200,
        json={"id": "cgt-test-123"},
        request=httpx.Request("POST", "https://example.test/tasks"),
    )

    async def fake_get(url, **kwargs):
        return list_response

    async def fake_post(url, **kwargs):
        return create_response

    client = AsyncMock()
    client.get = fake_get
    client.post = fake_post
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.seedance_health.ark_configured", return_value=True),
        patch("app.services.seedance_health.seedance_async_client", return_value=client),
        patch("app.services.seedance_health.delete_video_task", new=AsyncMock()),
    ):
        result = await check_seedance_credits(probe_billing=True)

    assert result["status"] == "ok"
    assert result["task_history"]["total_tasks"] == 3
    assert len(result["models"]) == 2
    assert all(m["billing_status"] == "ok" for m in result["models"])


@pytest.mark.asyncio
async def test_check_seedance_no_credits():
    list_response = httpx.Response(
        200,
        json={"total": 1, "items": []},
        request=httpx.Request("GET", "https://example.test/tasks"),
    )
    create_response = httpx.Response(
        402,
        text='{"error":{"code":"AccountOverdueError","message":"overdue balance"}}',
        request=httpx.Request("POST", "https://example.test/tasks"),
    )

    async def fake_get(url, **kwargs):
        return list_response

    async def fake_post(url, **kwargs):
        return create_response

    client = AsyncMock()
    client.get = fake_get
    client.post = fake_post
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.seedance_health.ark_configured", return_value=True),
        patch("app.services.seedance_health.seedance_async_client", return_value=client),
    ):
        result = await check_seedance_credits(probe_billing=True)

    assert result["status"] == "no_credits"
    assert all(m["billing_status"] == "no_credits" for m in result["models"])
