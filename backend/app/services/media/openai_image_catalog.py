"""Official OpenAI Images API models (direct, not via Runway / Higgsfield)."""

from __future__ import annotations

import logging
import re
import time
from threading import Lock

import httpx

from app.core.config import settings
from app.schemas.generation import GenerationModelOption

logger = logging.getLogger(__name__)

# catalog_id, label, api_model, cost_usd, est_seconds
# DALL·E 2/3 were removed from the API on 2026-05-12; GPT Image series is current.
_KNOWN_OPENAI_IMAGE_MODELS: list[tuple[str, str, str, float, int]] = [
    ("openai-gpt-image-2", "GPT Image 2", "gpt-image-2", 0.05, 18),
    ("openai-gpt-image-1.5", "GPT Image 1.5", "gpt-image-1.5", 0.04, 20),
    ("openai-gpt-image-1", "GPT Image 1", "gpt-image-1", 0.04, 25),
    ("openai-gpt-image-1-mini", "GPT Image 1 Mini", "gpt-image-1-mini", 0.02, 16),
]

_LABELS = {api: label for _cid, label, api, _c, _s in _KNOWN_OPENAI_IMAGE_MODELS}
_COSTS = {api: cost for _cid, _l, api, cost, _s in _KNOWN_OPENAI_IMAGE_MODELS}
_SECS = {api: secs for _cid, _l, api, _c, secs in _KNOWN_OPENAI_IMAGE_MODELS}
_KNOWN_APIS = {api for _cid, _l, api, _c, _s in _KNOWN_OPENAI_IMAGE_MODELS}
_CATALOG_TO_API = {cid: api for cid, _l, api, _c, _s in _KNOWN_OPENAI_IMAGE_MODELS}

_LIVE_CACHE: tuple[float, list[str]] | None = None
_LIVE_LOCK = Lock()
_LIVE_TTL_SEC = 600
_SNAPSHOT_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def openai_configured() -> bool:
    return bool((settings.OPENAI_API_KEY or "").strip())


def is_openai_image_model(model: str | None) -> bool:
    key = (model or "").strip().lower()
    if not key:
        return False
    if key.startswith("openai-"):
        return True
    if key.startswith("gpt-image") or key.startswith("dall-e"):
        return True
    return False


def resolve_openai_image_model(model: str | None) -> str:
    key = (model or "").strip().lower()
    if key in _CATALOG_TO_API:
        return _CATALOG_TO_API[key]
    if key.startswith("openai-"):
        key = key[len("openai-") :]
    if key in _KNOWN_APIS or key.startswith("gpt-image") or key.startswith("dall-e"):
        return key
    return "gpt-image-2"


def openai_image_cost_usd(model: str | None) -> float:
    api = resolve_openai_image_model(model)
    return float(_COSTS.get(api, 0.04))


def _fetch_live_image_model_ids() -> list[str]:
    global _LIVE_CACHE
    if not openai_configured():
        return []
    now = time.time()
    with _LIVE_LOCK:
        if _LIVE_CACHE and now - _LIVE_CACHE[0] < _LIVE_TTL_SEC:
            return list(_LIVE_CACHE[1])

    ids: list[str] = []
    try:
        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}"}
        base = (settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        with httpx.Client(timeout=8.0) as client:
            response = client.get(f"{base}/models", headers=headers)
            response.raise_for_status()
            body = response.json()
        for item in body.get("data") or []:
            mid = str(item.get("id") or "").strip()
            low = mid.lower()
            if low.startswith("dall-e") or low.startswith("gpt-image"):
                ids.append(mid)
    except Exception as exc:
        logger.warning("Could not list OpenAI image models: %s", exc)

    with _LIVE_LOCK:
        _LIVE_CACHE = (now, ids)
    return ids


def openai_image_catalog_options() -> list[GenerationModelOption]:
    if not openai_configured():
        return []

    live = set(_fetch_live_image_model_ids())
    seen: set[str] = set()
    options: list[GenerationModelOption] = []

    def _add(catalog_id: str, label: str, api_model: str, cost: float, est: int) -> None:
        if api_model in seen:
            return
        seen.add(api_model)
        options.append(
            GenerationModelOption(
                id=catalog_id,
                label=label,
                provider_model=api_model,
                modality="image",
                provider="openai",
                cost_usd=cost,
                cost_unit="image",
                estimated_seconds=est,
            )
        )

    for catalog_id, label, api_model, cost, est in _KNOWN_OPENAI_IMAGE_MODELS:
        if live and api_model not in live:
            continue
        _add(catalog_id, label, api_model, cost, est)

    # If /v1/models did not list image ids (common) or the key could not list, still show known GPT Image models.
    if not options:
        for catalog_id, label, api_model, cost, est in _KNOWN_OPENAI_IMAGE_MODELS:
            _add(catalog_id, label, api_model, cost, est)

    for api_model in sorted(live):
        if api_model in seen or _SNAPSHOT_RE.search(api_model):
            continue
        pretty = _LABELS.get(api_model) or api_model.replace("-", " ").title()
        _add(
            f"openai-{api_model}",
            pretty,
            api_model,
            _COSTS.get(api_model, 0.04),
            _SECS.get(api_model, 22),
        )

    return options
