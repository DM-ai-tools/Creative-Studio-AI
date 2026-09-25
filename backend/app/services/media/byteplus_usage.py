"""Retain measured video tokens without inventing a provider invoice."""

from __future__ import annotations

from typing import Any


def video_task_usage(task: dict[str, Any], *, task_id: str, model: str) -> dict:
    usage = task.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    return {
        "task_id": task_id,
        "model": model,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cost_usd": None,
        "cost_status": "unavailable",
        "source": "BytePlus task response",
    }
