"""Retain measured video tokens without inventing a provider invoice."""

from __future__ import annotations

from typing import Any


def video_task_usage(task: dict[str, Any], *, task_id: str, model: str) -> dict:
    usage = task.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or 0)
    if total and not completion and not prompt:
        completion = total
    elif total and not completion:
        completion = max(0, total - prompt)
    return {
        "task_id": task_id,
        "model": model,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total or (prompt + completion),
        "cost_usd": None,
        "cost_status": "unavailable",
        "source": "BytePlus task response",
    }
