"""Admin-editable price table for API spend estimates.

Defaults live here. An admin can override any value from the Usage page; the
overrides are stored in the ``pricing_config`` table and merged over these
defaults. Cost functions in ``usage_tracker`` read prices only through this
module, so there is exactly one place where a rate is decided.
"""

from __future__ import annotations

import copy
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_ID = "rates"
_CACHE_TTL_SEC = 30.0

# USD per 1M completion tokens, online inference, from the official BytePlus ModelArk
# pricing page (https://ai.byteplus.com/ark/region:ap-southeast-1/docs/ModelArk/1544106).
# BytePlus does not return USD on task responses, so Seedance spend is always
# completion tokens x the rate for the clip's model and resolution.
#   no_video   = the task had no reference video as input
#   with_video = the task used a reference video as input (cheaper per token)
# The docs list one rate for "480p and 720p". Models that do not support 1080p
# repeat their 720p rate so every cell exists.
def _rates(
    no_video_720: float,
    with_video_720: float,
    no_video_1080: float | None = None,
    with_video_1080: float | None = None,
    no_video_4k: float | None = None,
    with_video_4k: float | None = None,
) -> dict[str, dict[str, float]]:
    low = {"no_video": no_video_720, "with_video": with_video_720}
    high = {
        "no_video": no_video_720 if no_video_1080 is None else no_video_1080,
        "with_video": with_video_720 if with_video_1080 is None else with_video_1080,
    }
    # Only Seedance 2.0 supports 4K (2160p); other models repeat their 1080p rate.
    top = {
        "no_video": high["no_video"] if no_video_4k is None else no_video_4k,
        "with_video": high["with_video"] if with_video_4k is None else with_video_4k,
    }
    return {"480p": dict(low), "720p": dict(low), "1080p": high, "2160p": top}


SEEDANCE_FAMILIES: dict[str, str] = {
    "2.5": "Seedance 2.5 (dreamina-seedance-2-5-260628)",
    "2.5-flash": "Seedance 2.5 Flash",
    "2.0": "Seedance 2.0 (dreamina-seedance-2-0-260128)",
    "2.0-fast": "Seedance 2.0 Fast",
    "2.0-mini": "Seedance 2.0 Mini",
    "1.0-pro": "Seedance 1.0 Pro",
    "1.0-pro-fast": "Seedance 1.0 Pro Fast",
}

DEFAULT_SEEDANCE_PER_M_TOKENS: dict[str, dict[str, dict[str, float]]] = {
    "2.5": _rates(10.70, 6.40, 11.70, 7.00),
    "2.5-flash": _rates(7.0, 4.3),
    "2.0": _rates(7.0, 4.3, 7.7, 4.7, 4.0, 2.4),
    "2.0-fast": _rates(5.6, 3.3),
    "2.0-mini": _rates(3.5, 2.1),
    "1.0-pro": _rates(2.5, 2.5),
    "1.0-pro-fast": _rates(1.0, 1.0),
}

# Longest / most specific marker first. Model ids look like
# "dreamina-seedance-2-5-260628" or "seedance-1-0-pro-250528".
_SEEDANCE_FAMILY_MARKERS: tuple[tuple[str, str], ...] = (
    ("2-5-flash", "2.5-flash"),
    ("2.5-flash", "2.5-flash"),
    ("2-0-fast", "2.0-fast"),
    ("2.0-fast", "2.0-fast"),
    ("2-0-mini", "2.0-mini"),
    ("2.0-mini", "2.0-mini"),
    ("1-0-pro-fast", "1.0-pro-fast"),
    ("1.0-pro-fast", "1.0-pro-fast"),
    ("1-0-pro", "1.0-pro"),
    ("1.0-pro", "1.0-pro"),
    ("2-5", "2.5"),
    ("2.5", "2.5"),
    ("2-0", "2.0"),
    ("2.0", "2.0"),
)


def seedance_family(model: str | None) -> str:
    """Pricing family for a Seedance model id (unknown ids use the 2.5 rates)."""
    text = (model or "").strip().lower()
    for marker, family in _SEEDANCE_FAMILY_MARKERS:
        if marker in text:
            return family
    return "2.5"


DEFAULT_LLM_PER_M_TOKENS: dict[str, dict[str, float]] = {
    "anthropic/claude-haiku-4.5": {"input": 1.0, "output": 5.0},
    "anthropic/claude-sonnet-4.6": {"input": 3.0, "output": 15.0},
    "anthropic/claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai/gpt-4o": {"input": 2.50, "output": 10.0},
    "google/gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "google/gemini-3.1-flash-image-preview": {"input": 0.30, "output": 2.50},
    "google/veo-3.1": {"input": 0.0, "output": 0.0},
}

DEFAULTS: dict[str, Any] = {
    "seedance_per_m_tokens": DEFAULT_SEEDANCE_PER_M_TOKENS,
    # Used only when a Seedance row has no token count at all.
    "seedance_fallback_usd_per_30s": 17.0,
    "llm_per_m_tokens": DEFAULT_LLM_PER_M_TOKENS,
    # Applied to LLM models that are not listed above.
    "llm_default_per_m_tokens": {"input": 0.50, "output": 2.00},
    # OpenAI image model (API id) -> USD per image. Empty = use catalog price.
    "image_usd_each": {},
}

_overrides: dict[str, Any] = {}
_loaded_at: float = 0.0


def _merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        merged = copy.deepcopy(base)
        for key, value in over.items():
            merged[key] = _merge(base.get(key), value) if key in base else copy.deepcopy(value)
        return merged
    return copy.deepcopy(over)


def get_pricing() -> dict[str, Any]:
    """Defaults with the current admin overrides applied."""
    return _merge(DEFAULTS, _overrides) if _overrides else copy.deepcopy(DEFAULTS)


def get_overrides() -> dict[str, Any]:
    return copy.deepcopy(_overrides)


def set_overrides(data: dict[str, Any] | None) -> None:
    global _overrides, _loaded_at
    _overrides = copy.deepcopy(data or {})
    _loaded_at = time.monotonic()


class PricingValidationError(ValueError):
    pass


def _num(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise PricingValidationError(f"{label} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise PricingValidationError(f"{label} must be a number") from None
    if number != number or number < 0 or number > 10_000:
        raise PricingValidationError(f"{label} must be between 0 and 10000")
    return round(number, 6)


def validate_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a cleaned copy of an override document or raise."""
    if not isinstance(payload, dict):
        raise PricingValidationError("Pricing must be an object")
    clean: dict[str, Any] = {}

    seedance = payload.get("seedance_per_m_tokens")
    if seedance is not None:
        if not isinstance(seedance, dict):
            raise PricingValidationError("seedance_per_m_tokens must be an object")
        out: dict[str, dict[str, dict[str, float]]] = {}
        for family, by_res in seedance.items():
            if family not in DEFAULT_SEEDANCE_PER_M_TOKENS:
                raise PricingValidationError(f"Unknown Seedance model: {family}")
            if not isinstance(by_res, dict):
                raise PricingValidationError(f"Seedance {family} rates must be an object")
            out[family] = {}
            for res, rates in by_res.items():
                if res not in ("480p", "720p", "1080p", "2160p"):
                    raise PricingValidationError(f"Unknown Seedance resolution: {res}")
                if not isinstance(rates, dict):
                    raise PricingValidationError(f"Seedance {family} {res} rates must be an object")
                out[family][res] = {}
                for kind in ("no_video", "with_video"):
                    if kind in rates:
                        out[family][res][kind] = _num(rates[kind], f"Seedance {family} {res} {kind}")
        clean["seedance_per_m_tokens"] = out

    if "seedance_fallback_usd_per_30s" in payload:
        clean["seedance_fallback_usd_per_30s"] = _num(
            payload["seedance_fallback_usd_per_30s"], "Seedance fallback per 30s"
        )

    llm = payload.get("llm_per_m_tokens")
    if llm is not None:
        if not isinstance(llm, dict):
            raise PricingValidationError("llm_per_m_tokens must be an object")
        out_llm: dict[str, dict[str, float]] = {}
        for model, rates in llm.items():
            name = str(model).strip().lower()
            if not name or len(name) > 160:
                raise PricingValidationError("Invalid LLM model name")
            if not isinstance(rates, dict):
                raise PricingValidationError(f"{name} rates must be an object")
            out_llm[name] = {
                "input": _num(rates.get("input", 0), f"{name} input"),
                "output": _num(rates.get("output", 0), f"{name} output"),
            }
        clean["llm_per_m_tokens"] = out_llm

    default_llm = payload.get("llm_default_per_m_tokens")
    if default_llm is not None:
        if not isinstance(default_llm, dict):
            raise PricingValidationError("llm_default_per_m_tokens must be an object")
        clean["llm_default_per_m_tokens"] = {
            "input": _num(default_llm.get("input", 0), "Default LLM input"),
            "output": _num(default_llm.get("output", 0), "Default LLM output"),
        }

    images = payload.get("image_usd_each")
    if images is not None:
        if not isinstance(images, dict):
            raise PricingValidationError("image_usd_each must be an object")
        clean["image_usd_each"] = {
            str(model).strip().lower(): _num(price, f"{model} price")
            for model, price in images.items()
            if str(model).strip()
        }
    return clean


# ── accessors used by usage_tracker ───────────────────────────────────────────


def seedance_rate(model: str | None, resolution: str, *, with_video: bool) -> float:
    table = get_pricing()["seedance_per_m_tokens"]
    by_res = table.get(seedance_family(model)) or table["2.5"]
    row = by_res.get(resolution) or by_res.get("720p") or by_res["1080p"]
    return float(row["with_video" if with_video else "no_video"])


def seedance_fallback_usd_per_30s() -> float:
    return float(get_pricing()["seedance_fallback_usd_per_30s"])


def llm_rates(model_key: str) -> tuple[float, float]:
    pricing = get_pricing()
    table = pricing["llm_per_m_tokens"]
    rates = table.get(model_key)
    if rates is None:
        for known, pair in table.items():
            if known in model_key or model_key in known:
                rates = pair
                break
    if rates is None:
        rates = pricing["llm_default_per_m_tokens"]
    return float(rates["input"]), float(rates["output"])


def image_price_override(api_model: str) -> float | None:
    value = get_pricing()["image_usd_each"].get((api_model or "").strip().lower())
    return float(value) if value is not None else None


# ── persistence ───────────────────────────────────────────────────────────────


async def load_overrides_from_db(db=None) -> dict[str, Any]:
    """Read overrides from the database into the process cache."""
    from sqlalchemy import select

    from app.models.pricing_config import PricingConfig

    async def _read(session) -> dict[str, Any]:
        row = (
            await session.execute(select(PricingConfig).where(PricingConfig.id == _CONFIG_ID))
        ).scalar_one_or_none()
        return dict(row.data or {}) if row else {}

    try:
        if db is not None:
            data = await _read(db)
        else:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                data = await _read(session)
    except Exception:
        logger.warning("Could not load pricing overrides; keeping the current ones", exc_info=True)
        return get_overrides()
    set_overrides(data)
    return data


async def refresh_if_stale() -> None:
    """Re-read overrides when the cache is older than the TTL (multi-worker safe)."""
    if time.monotonic() - _loaded_at > _CACHE_TTL_SEC:
        await load_overrides_from_db()


async def save_overrides_to_db(db, data: dict[str, Any], *, user_id=None) -> dict[str, Any]:
    from sqlalchemy import select

    from app.models.pricing_config import PricingConfig

    row = (
        await db.execute(select(PricingConfig).where(PricingConfig.id == _CONFIG_ID))
    ).scalar_one_or_none()
    if row is None:
        row = PricingConfig(id=_CONFIG_ID, data=data, updated_by=user_id)
        db.add(row)
    else:
        row.data = data
        row.updated_by = user_id
    await db.flush()
    set_overrides(data)
    return data
