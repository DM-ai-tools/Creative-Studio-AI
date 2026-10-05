"""Lightweight BytePlus Seedance billing / connectivity probe for admin."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from app.services.media.byteplus_seedance_client import (
    ark_base_url,
    ark_configured,
    ark_headers,
    ark_seedance_25_model,
    ark_seedance_model,
    delete_video_task,
    seedance_async_client,
)

SeedanceCheckStatus = Literal[
    "ok",
    "no_credits",
    "not_configured",
    "auth_error",
    "connection_error",
    "error",
]

_BILLING_MARKERS = (
    "accountoverdueerror",
    "overdue balance",
    "insufficient balance",
    "insufficient funds",
)


def _classify_billing_error(body: str) -> bool:
    low = (body or "").lower()
    return any(marker in low for marker in _BILLING_MARKERS)


def _model_rows() -> list[dict[str, str]]:
    return [
        {
            "catalog_id": "ark-seedance-2-0",
            "label": "Seedance 2.0",
            "api_model": ark_seedance_model(),
        },
        {
            "catalog_id": "ark-seedance-2-5",
            "label": "Seedance 2.5",
            "api_model": ark_seedance_25_model(),
        },
    ]


async def _list_recent_tasks(client: httpx.AsyncClient) -> dict[str, Any]:
    url = f"{ark_base_url()}/contents/generations/tasks?page_size=10"
    response = await client.get(url, headers=ark_headers(), timeout=30.0)
    if response.status_code in {401, 403}:
        raise PermissionError((response.text or "")[:400])
    if response.status_code >= 400:
        raise RuntimeError(f"Task list failed ({response.status_code}): {(response.text or '')[:400]}")
    data = response.json() if response.content else {}
    items = data.get("items") if isinstance(data, dict) else []
    if not isinstance(items, list):
        items = []
    succeeded = sum(
        1
        for item in items
        if isinstance(item, dict)
        and str(item.get("status") or "").lower() in {"succeeded", "success", "completed", "done"}
    )
    failed = sum(
        1
        for item in items
        if isinstance(item, dict)
        and str(item.get("status") or "").lower() in {"failed", "error", "cancelled", "canceled"}
    )
    billing_failures = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        err_blob = str(item.get("error") or item.get("message") or item.get("fail_reason") or "")
        if _classify_billing_error(err_blob):
            billing_failures += 1
    return {
        "total_tasks": int(data.get("total") or 0) if isinstance(data, dict) else 0,
        "recent_succeeded": succeeded,
        "recent_failed": failed,
        "recent_billing_failures": billing_failures,
    }


async def _probe_model_billing(
    client: httpx.AsyncClient,
    *,
    catalog_id: str,
    label: str,
    api_model: str,
) -> dict[str, Any]:
    payload = {
        "model": api_model,
        "content": [{"type": "text", "text": "admin billing probe — slow product pan"}],
        "duration": 4,
        "ratio": "9:16",
        "resolution": "720p",
        "generate_audio": False,
        "watermark": False,
    }
    url = f"{ark_base_url()}/contents/generations/tasks"
    try:
        response = await client.post(url, json=payload, headers=ark_headers(), timeout=60.0)
    except httpx.RequestError as exc:
        return {
            "catalog_id": catalog_id,
            "label": label,
            "api_model": api_model,
            "billing_status": "connection_error",
            "message": f"Could not reach BytePlus: {exc}",
        }

    body = response.text or ""
    if response.status_code in {401, 403}:
        return {
            "catalog_id": catalog_id,
            "label": label,
            "api_model": api_model,
            "billing_status": "auth_error",
            "message": "BytePlus rejected the API key.",
        }
    if _classify_billing_error(body):
        return {
            "catalog_id": catalog_id,
            "label": label,
            "api_model": api_model,
            "billing_status": "no_credits",
            "message": "BytePlus account has overdue or insufficient balance.",
        }
    if response.status_code >= 400:
        return {
            "catalog_id": catalog_id,
            "label": label,
            "api_model": api_model,
            "billing_status": "error",
            "message": f"Billing probe failed ({response.status_code}): {body[:300]}",
        }

    data = response.json() if response.content else {}
    task_id = str(data.get("id") or data.get("task_id") or "").strip()
    if task_id:
        try:
            await delete_video_task(task_id, client=client)
        except Exception:
            pass
    return {
        "catalog_id": catalog_id,
        "label": label,
        "api_model": api_model,
        "billing_status": "ok",
        "message": "Billing accepted — test task cancelled immediately.",
        "probe_task_id": task_id or None,
    }


async def check_seedance_credits(*, probe_billing: bool = True) -> dict[str, Any]:
    """Return Seedance connectivity + billing status for admin UI."""
    checked_at = datetime.now(timezone.utc)
    if not ark_configured():
        return {
            "checked_at": checked_at.isoformat(),
            "configured": False,
            "status": "not_configured",
            "message": "ARK_API_KEY is not set — add your BytePlus ModelArk key in backend .env.",
            "task_history": None,
            "models": [],
        }

    async with seedance_async_client() as client:
        try:
            task_history = await _list_recent_tasks(client)
        except PermissionError:
            return {
                "checked_at": checked_at.isoformat(),
                "configured": True,
                "status": "auth_error",
                "message": "BytePlus rejected the API key.",
                "task_history": None,
                "models": [],
            }
        except httpx.RequestError as exc:
            return {
                "checked_at": checked_at.isoformat(),
                "configured": True,
                "status": "connection_error",
                "message": f"Could not reach BytePlus: {exc}",
                "task_history": None,
                "models": [],
            }
        except Exception as exc:
            return {
                "checked_at": checked_at.isoformat(),
                "configured": True,
                "status": "error",
                "message": str(exc)[:400],
                "task_history": None,
                "models": [],
            }

        models: list[dict[str, Any]] = []
        if probe_billing:
            for row in _model_rows():
                models.append(await _probe_model_billing(client, **row))
        else:
            for row in _model_rows():
                models.append(
                    {
                        **row,
                        "billing_status": "skipped",
                        "message": "Billing probe skipped.",
                    }
                )

    billing_statuses = {m.get("billing_status") for m in models if m.get("billing_status") != "skipped"}
    if "no_credits" in billing_statuses:
        overall: SeedanceCheckStatus = "no_credits"
        message = "BytePlus billing is blocked — recharge your account to use Seedance."
    elif billing_statuses == {"ok"} or (billing_statuses <= {"ok"} and "ok" in billing_statuses):
        overall = "ok"
        message = "Seedance billing is active for all probed models."
    elif "auth_error" in billing_statuses:
        overall = "auth_error"
        message = "BytePlus rejected the API key."
    elif "connection_error" in billing_statuses:
        overall = "connection_error"
        message = "Could not reach BytePlus during billing probe."
    elif billing_statuses:
        overall = "error"
        message = "Seedance billing probe returned an unexpected error."
    elif task_history.get("recent_billing_failures"):
        overall = "no_credits"
        message = "Recent Seedance tasks failed with billing errors."
    elif task_history.get("recent_succeeded", 0) > 0:
        overall = "ok"
        message = "BytePlus API connected — recent Seedance clips succeeded."
    else:
        overall = "ok"
        message = "BytePlus API connected."

    return {
        "checked_at": checked_at.isoformat(),
        "configured": True,
        "status": overall,
        "message": message,
        "task_history": task_history,
        "models": models,
        "probe_note": (
            "Billing probe submits a 4s text-only task and cancels it immediately if accepted. "
            "BytePlus may still charge a small amount."
            if probe_billing
            else None
        ),
    }
