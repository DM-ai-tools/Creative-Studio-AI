"""Async wrapper around the official higgsfield-client SDK."""

from __future__ import annotations

import logging
import os
from typing import Any

import higgsfield_client

from app.core.config import settings

logger = logging.getLogger(__name__)


def _ensure_credentials_env() -> None:
    key = (settings.HIGGSFIELD_API_KEY or "").strip()
    secret = (settings.HIGGSFIELD_API_SECRET or "").strip()
    if not key or not secret:
        raise RuntimeError(
            "Higgsfield API is not configured. Set HIGGSFIELD_API_KEY and HIGGSFIELD_API_SECRET in .env"
        )
    os.environ["HF_API_KEY"] = key
    os.environ["HF_API_SECRET"] = secret
    os.environ["HF_KEY"] = f"{key}:{secret}"


def extract_media_url(result: dict[str, Any]) -> str | None:
    images = result.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict) and first.get("url"):
            return str(first["url"])
    video = result.get("video")
    if isinstance(video, dict) and video.get("url"):
        return str(video["url"])
    jobs = result.get("jobs")
    if isinstance(jobs, list):
        for job in jobs:
            if not isinstance(job, dict):
                continue
            results = job.get("results")
            if isinstance(results, dict):
                raw = results.get("raw")
                if isinstance(raw, dict) and raw.get("url"):
                    return str(raw["url"])
    return None


async def subscribe_platform(
    platform_path: str,
    arguments: dict[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    _ensure_credentials_env()
    path = platform_path.lstrip("/")
    logger.info("Higgsfield %s: path=%s", label, path)
    try:
        return await higgsfield_client.subscribe_async(path, arguments)
    except Exception as exc:
        msg = str(exc)
        if "not_enough_credits" in msg:
            raise RuntimeError(
                "Higgsfield account has insufficient credits. Top up at https://cloud.higgsfield.ai"
            ) from exc
        if "Model not found" in msg:
            raise RuntimeError(
                f"Higgsfield model path not available on your account: {path}. "
                "Try another model or check https://docs.higgsfield.ai"
            ) from exc
        raise RuntimeError(f"Higgsfield generation failed: {msg}") from exc


async def upload_local_image(file_path: str) -> str:
    _ensure_credentials_env()
    return await higgsfield_client.upload_file_async(file_path)
