"""Track tokens, credits, and estimated USD spend across connected APIs."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_ctx: ContextVar[dict[str, Any] | None] = ContextVar("usage_ctx", default=None)
_openai_patched = False

# USD per 1M tokens — approximate list prices used when the provider does not return cost.
_LLM_PRICE_PER_M: dict[str, tuple[float, float]] = {
    "anthropic/claude-haiku-4.5": (1.0, 5.0),
    "anthropic/claude-sonnet-4.6": (3.0, 15.0),
    "anthropic/claude-sonnet-4": (3.0, 15.0),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.50, 10.0),
    "google/gemini-2.5-flash": (0.15, 0.60),
    "google/gemini-3.1-flash-image-preview": (0.30, 2.50),
    "google/veo-3.1": (0.0, 0.0),
}

_FIRECRAWL_SCRAPE_USD = 0.005
_META_EXPORT_USD = 0.0
_RUNWAY_CREDIT_USD = 0.01


def get_usage_context() -> dict[str, Any]:
    return dict(_ctx.get() or {})


def set_usage_context(**kwargs: Any) -> None:
    current = dict(_ctx.get() or {})
    current.update({k: v for k, v in kwargs.items() if v is not None})
    _ctx.set(current)


@contextmanager
def usage_context(**kwargs: Any):
    token = _ctx.set({**get_usage_context(), **kwargs})
    try:
        yield
    finally:
        _ctx.reset(token)


def _as_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None


def estimate_llm_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    key = (model or "").strip().lower()
    prices = _LLM_PRICE_PER_M.get(key)
    if not prices:
        for known, pair in _LLM_PRICE_PER_M.items():
            if known in key or key in known:
                prices = pair
                break
    if not prices:
        prices = (0.50, 2.00)
    inp, out = prices
    return round((prompt_tokens / 1_000_000) * inp + (completion_tokens / 1_000_000) * out, 6)


def estimate_media_cost(*, provider: str, model: str, duration_seconds: float = 0) -> tuple[float, float]:
    """Return (cost_usd, credits). Credits are Runway-style (1 credit ≈ $0.01) when known."""
    provider = (provider or "").lower()
    model = (model or "").lower()
    duration = max(float(duration_seconds or 0), 0.0)

    if provider == "runway":
        from app.services.media.runway_catalog import RUNWAY_IMAGE_MODELS, RUNWAY_VIDEO_MODELS

        for catalog_id, _label, api_model, credits, _est in RUNWAY_IMAGE_MODELS:
            if model in {catalog_id, api_model, api_model.replace(".", "_")}:
                return round(credits * _RUNWAY_CREDIT_USD, 6), float(credits)
        for catalog_id, _label, api_model, credits_per_sec, _est in RUNWAY_VIDEO_MODELS:
            if model in {catalog_id, api_model} or model.startswith(catalog_id):
                secs = duration or 8
                credits = credits_per_sec * secs
                return round(credits * _RUNWAY_CREDIT_USD, 6), float(credits)

    if provider == "heygen":
        per_sec = 0.05 if "v3" in model or "agent" in model else 0.04
        secs = duration or 8
        cost = per_sec * secs
        return round(cost, 6), round(cost / _RUNWAY_CREDIT_USD, 4)

    if provider == "higgsfield":
        secs = duration or 5
        cost = 0.08 * secs if any(k in model for k in ("video", "veo", "kling", "dop", "seedance")) else 0.10
        if "nano" in model:
            cost = 0.07
        return round(cost, 6), round(cost / _RUNWAY_CREDIT_USD, 4)

    if provider == "byteplus":
        # Video token pricing depends on the model/resolution/account rate.
        # No Runway-equivalent credits or guessed per-second charge.
        return 0.0, 0.0

    if provider == "openai":
        from app.services.media.openai_image_catalog import openai_image_cost_usd

        cost = openai_image_cost_usd(model)
        return round(cost, 6), round(cost / _RUNWAY_CREDIT_USD, 4)

    return 0.0, 0.0


# BytePlus Seedance — USD per 1M completion tokens (public list pricing).
_BYTEPLUS_SEEDANCE_720_NO_VIDEO = 10.70
_BYTEPLUS_SEEDANCE_720_WITH_VIDEO = 6.40
_BYTEPLUS_SEEDANCE_1080_NO_VIDEO = 11.70
_BYTEPLUS_SEEDANCE_1080_WITH_VIDEO = 7.00
_SEEDANCE_PRICING_NOTE = (
    "BytePlus does not return USD on task responses; estimates use public Seedance "
    "token rates ($6.40–$10.70 per 1M completion tokens at 720p)."
)


def is_byteplus_seedance_row(row: Any) -> bool:
    prov = (getattr(row, "provider", "") or "").lower()
    op = (getattr(row, "operation", "") or "").lower()
    model = (getattr(row, "model", "") or "").lower()
    return prov == "byteplus" and op == "video_generation" and ("seedance" in model or "dreamina" in model)


def _row_completion_tokens(row: Any) -> int:
    return int(getattr(row, "completion_tokens", 0) or getattr(row, "total_tokens", 0) or 0)


def estimate_byteplus_seedance_cost_usd(
    tokens: int,
    *,
    with_video_input: bool | None = None,
    resolution_1080: bool = False,
) -> dict[str, float]:
    """Return low/high/mid USD estimates from measured completion tokens."""
    count = max(0, int(tokens or 0))
    if count == 0:
        return {"low": 0.0, "high": 0.0, "mid": 0.0}
    if resolution_1080:
        lo_rate = _BYTEPLUS_SEEDANCE_1080_WITH_VIDEO
        hi_rate = _BYTEPLUS_SEEDANCE_1080_NO_VIDEO
    else:
        lo_rate = _BYTEPLUS_SEEDANCE_720_WITH_VIDEO
        hi_rate = _BYTEPLUS_SEEDANCE_720_NO_VIDEO
    if with_video_input is True:
        low_rate, high_rate = lo_rate, lo_rate
    elif with_video_input is False:
        low_rate, high_rate = hi_rate, hi_rate
    else:
        low_rate, high_rate = lo_rate, hi_rate
    low_usd = round(count / 1_000_000 * low_rate, 4)
    high_usd = round(count / 1_000_000 * high_rate, 4)
    return {"low": low_usd, "high": high_usd, "mid": round((low_usd + high_usd) / 2, 4)}


def seedance_cost_detail(row: Any) -> dict[str, float] | None:
    if not is_byteplus_seedance_row(row):
        return None
    extra = getattr(row, "extra", None) or {}
    resolution = str(extra.get("resolution") or "").lower()
    resolution_1080 = "1080" in resolution
    with_video = extra.get("with_video_input")
    if with_video is not None:
        with_video_input = bool(with_video)
    else:
        with_video_input = None
    return estimate_byteplus_seedance_cost_usd(
        _row_completion_tokens(row),
        with_video_input=with_video_input,
        resolution_1080=resolution_1080,
    )


def effective_cost_usd(row: Any) -> float:
    stored = float(getattr(row, "cost_usd", 0) or 0)
    if stored > 0:
        return stored
    if is_byteplus_seedance_row(row) and getattr(row, "success", False):
        detail = seedance_cost_detail(row)
        return float(detail["mid"]) if detail else 0.0
    return 0.0


def _build_seedance_summary(rows: list[Any], *, tenant_names: dict[UUID, str]) -> dict[str, Any]:
    seedance_rows = [r for r in rows if is_byteplus_seedance_row(r)]
    successful = [r for r in seedance_rows if r.success]
    failed = [r for r in seedance_rows if not r.success]

    cost_low = 0.0
    cost_high = 0.0
    total_tokens = 0
    for row in successful:
        total_tokens += _row_completion_tokens(row)
        detail = seedance_cost_detail(row) or {"low": 0.0, "high": 0.0}
        cost_low += detail["low"]
        cost_high += detail["high"]

    by_model: dict[str, dict[str, Any]] = {}
    for row in seedance_rows:
        model = row.model or "unknown"
        slot = by_model.setdefault(
            model,
            {
                "model": model,
                "clips": 0,
                "failed": 0,
                "tokens": 0,
                "cost_usd_low": 0.0,
                "cost_usd_high": 0.0,
            },
        )
        if row.success:
            slot["clips"] += 1
            slot["tokens"] += _row_completion_tokens(row)
            detail = seedance_cost_detail(row) or {"low": 0.0, "high": 0.0}
            slot["cost_usd_low"] += detail["low"]
            slot["cost_usd_high"] += detail["high"]
        else:
            slot["failed"] += 1

    model_rows = list(by_model.values())
    for slot in model_rows:
        slot["cost_usd_low"] = round(slot["cost_usd_low"], 4)
        slot["cost_usd_high"] = round(slot["cost_usd_high"], 4)
        slot["cost_usd"] = round((slot["cost_usd_low"] + slot["cost_usd_high"]) / 2, 4)
    model_rows.sort(key=lambda x: x["tokens"], reverse=True)

    recent_clips: list[dict[str, Any]] = []
    for row in successful[:40]:
        extra = row.extra or {}
        detail = seedance_cost_detail(row) or {"low": 0.0, "high": 0.0, "mid": 0.0}
        recent_clips.append(
            {
                "id": str(row.id),
                "task_id": extra.get("task_id"),
                "model": row.model,
                "tokens": _row_completion_tokens(row),
                "cost_usd_low": detail["low"],
                "cost_usd_high": detail["high"],
                "cost_usd": detail["mid"],
                "cost_estimated": float(row.cost_usd or 0) <= 0,
                "recovered": bool(extra.get("recovered")),
                "client": tenant_names.get(row.tenant_id) if row.tenant_id else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )

    return {
        "successful_clips": len(successful),
        "failed_calls": len(failed),
        "total_tokens": total_tokens,
        "cost_usd_low": round(cost_low, 4),
        "cost_usd_high": round(cost_high, 4),
        "cost_usd": round((cost_low + cost_high) / 2, 4),
        "pricing_note": _SEEDANCE_PRICING_NOTE,
        "by_model": model_rows,
        "recent_clips": recent_clips,
    }


def record_usage(
    *,
    provider: str,
    model: str = "",
    operation: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    credits: float = 0,
    cost_usd: float = 0,
    success: bool = True,
    error: str | None = None,
    extra: dict | None = None,
    tenant_id: Any = None,
    user_id: Any = None,
) -> None:
    ctx = get_usage_context()
    payload = {
        "tenant_id": _as_uuid(tenant_id if tenant_id is not None else ctx.get("tenant_id")),
        "user_id": _as_uuid(user_id if user_id is not None else ctx.get("user_id")),
        "provider": (provider or "unknown")[:50],
        "model": (model or "")[:160],
        "operation": (operation or ctx.get("operation") or "")[:160],
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or (prompt_tokens or 0) + (completion_tokens or 0)),
        "credits": float(credits or 0),
        "cost_usd": float(cost_usd or 0),
        "success": bool(success),
        "error": (error or "")[:2000] or None,
        "extra": extra or {},
    }
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_persist_usage(payload))
    except RuntimeError:
        threading.Thread(target=_persist_usage_sync, args=(payload,), daemon=True).start()


def _persist_usage_sync(payload: dict) -> None:
    try:
        asyncio.run(_persist_usage(payload))
    except Exception:
        logger.debug("usage persist sync failed", exc_info=True)


async def _persist_usage(payload: dict) -> None:
    try:
        from app.models.usage_event import UsageEvent

        async with AsyncSessionLocal() as db:
            db.add(UsageEvent(**payload))
            await db.commit()
    except Exception:
        logger.debug("usage persist failed", exc_info=True)


def record_llm_response(response: Any, *, model: str, operation: str = "llm") -> None:
    usage = getattr(response, "usage", None)
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
    completion = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
    total = int(getattr(usage, "total_tokens", 0) or 0) if usage else (prompt + completion)
    native_cost = None
    if usage is not None:
        native_cost = getattr(usage, "cost", None)
        if native_cost is None and isinstance(usage, dict):
            native_cost = usage.get("cost")
            prompt = int(usage.get("prompt_tokens") or prompt)
            completion = int(usage.get("completion_tokens") or completion)
            total = int(usage.get("total_tokens") or total)
    try:
        cost = float(native_cost) if native_cost is not None else estimate_llm_cost(model, prompt, completion)
    except (TypeError, ValueError):
        cost = estimate_llm_cost(model, prompt, completion)
    record_usage(
        provider="openrouter",
        model=model,
        operation=operation,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        credits=round(cost / _RUNWAY_CREDIT_USD, 4) if cost else 0,
        cost_usd=cost,
        success=True,
    )


def record_media_generation(
    *,
    provider: str,
    model: str,
    operation: str,
    success: bool,
    duration_seconds: float = 0,
    error: str | None = None,
    extra: dict | None = None,
    tenant_id: Any = None,
) -> None:
    cost, credits = estimate_media_cost(
        provider=provider, model=model, duration_seconds=duration_seconds
    )
    if not success:
        cost, credits = 0.0, 0.0
    record_usage(
        provider=provider,
        model=model,
        operation=operation,
        credits=credits,
        cost_usd=cost,
        success=success,
        error=error,
        extra=extra,
        tenant_id=tenant_id,
    )


def record_firecrawl(*, success: bool, url: str = "", error: str | None = None) -> None:
    record_usage(
        provider="firecrawl",
        model="scrape",
        operation="fetch_brand_from_url",
        credits=0.5 if success else 0,
        cost_usd=_FIRECRAWL_SCRAPE_USD if success else 0,
        success=success,
        error=error,
        extra={"url": url[:300]} if url else None,
    )


def record_sociavault(
    *,
    success: bool,
    platform: str = "",
    handle: str = "",
    post_count: int = 0,
    error: str | None = None,
) -> None:
    record_usage(
        provider="sociavault",
        model=platform or "social",
        operation="fetch_social_style",
        credits=float(post_count or 1) if success else 0,
        cost_usd=0.01 * max(1, post_count) if success else 0,
        success=success,
        error=error,
        extra={"platform": platform, "handle": handle[:120]} if platform or handle else None,
    )


def record_meta_export(*, success: bool, variant_count: int = 0, error: str | None = None) -> None:
    record_usage(
        provider="meta",
        model="graph_api",
        operation="export_variants",
        cost_usd=_META_EXPORT_USD,
        success=success,
        error=error,
        extra={"variant_count": variant_count},
    )


def install_openai_tracking() -> None:
    """Patch openai.OpenAI so every chat.completions.create is logged."""
    global _openai_patched
    if _openai_patched:
        return
    try:
        import openai
    except ImportError:
        return

    original = openai.OpenAI

    class TrackedOpenAI(original):  # type: ignore[valid-type,misc]
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)
            base = str(kwargs.get("base_url") or getattr(self, "base_url", "") or "")
            if "openrouter" not in base.lower() and "openrouter" not in str(
                getattr(self, "base_url", "")
            ).lower():
                # Still wrap — CreativeStudio uses OpenRouter for all chat models.
                pass
            _patch_chat_create(self)

    openai.OpenAI = TrackedOpenAI  # type: ignore[misc]
    _openai_patched = True
    logger.info("OpenAI/OpenRouter usage tracking installed")


def _patch_chat_create(client: Any) -> None:
    try:
        completions = client.chat.completions
        original_create = completions.create
    except Exception:
        return

    def tracked_create(*args: Any, **kwargs: Any):
        model = str(kwargs.get("model") or "")
        operation = get_usage_context().get("operation") or "chat.completions"
        try:
            response = original_create(*args, **kwargs)
            record_llm_response(response, model=model, operation=operation)
            return response
        except Exception as exc:
            record_usage(
                provider="openrouter",
                model=model,
                operation=operation,
                success=False,
                error=str(exc)[:2000],
            )
            raise

    completions.create = tracked_create


_CHART_DAYS = 30
_MAX_CHART_MODELS = 7

_MODEL_LABELS: dict[str, str] = {
    "claude-haiku-4.5": "Claude Haiku",
    "claude-sonnet-4.6": "Claude Sonnet 4.6",
    "claude-sonnet-4": "Claude Sonnet 4",
    "gpt-4o-mini": "GPT-4o Mini",
    "gpt-4o": "GPT-4o",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-3.1-flash-image-preview": "Gemini 3.1 Flash",
    "gemini_image3.1_flash": "Gemini 3.1 Image",
    "gemini_image3_pro": "Gemini 3 Pro Image",
    "veo3.1": "Veo 3.1",
    "seedance-2-5": "Seedance 2.5",
    "seedance-2-0": "Seedance 2.0",
    "seedance-1-5": "Seedance 1.5",
    "scrape": "Firecrawl",
    "graph_api": "Meta Graph",
}


def _display_model(model: str, provider: str = "") -> str:
    raw = (model or "").strip()
    prov = (provider or "").strip().lower()
    if not raw:
        if prov == "firecrawl":
            return "Firecrawl"
        if prov == "runway":
            return "Runway"
        if prov == "heygen":
            return "HeyGen"
        if prov == "meta":
            return "Meta"
        if prov == "byteplus":
            return "Seedance"
        return prov.title() or "Other"
    short = raw.split("/")[-1] if "/" in raw else raw
    key = short.lower().replace("_", "-")
    for needle, label in _MODEL_LABELS.items():
        if needle in key or key in needle:
            return label
    cleaned = short.replace("-", " ").replace("_", " ")
    return cleaned[:36].title()


def _build_daily_series(
    rows: list[Any],
    *,
    value_fn: Callable[[Any], float],
    days: int = _CHART_DAYS,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Daily stacked series — top models + Other bucket."""
    today = datetime.now(timezone.utc).date()
    day_keys = [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]
    by_day: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    model_totals: dict[str, float] = defaultdict(float)

    for r in rows:
        if not r.created_at:
            continue
        day = r.created_at.astimezone(timezone.utc).date().isoformat()
        label = _display_model(r.model, r.provider)
        val = float(value_fn(r) or 0)
        by_day[day][label] += val
        model_totals[label] += val

    top = [
        m
        for m, _ in sorted(model_totals.items(), key=lambda x: x[1], reverse=True)
        if model_totals[m] > 0
    ][:_MAX_CHART_MODELS]
    legend = list(top)
    has_other = len(model_totals) > len(top)
    if has_other:
        legend.append("Other")

    series: list[dict[str, Any]] = []
    for day in day_keys:
        point: dict[str, Any] = {"date": day, "total": 0.0}
        other = 0.0
        for m in top:
            v = by_day[day].get(m, 0.0)
            point[m] = round(v, 4)
            point["total"] += v
        for m, v in by_day[day].items():
            if m not in top:
                other += v
        if has_other:
            point["Other"] = round(other, 4)
            point["total"] += other
        point["total"] = round(point["total"], 4)
        series.append(point)
    return series, legend


def _align_series_to_legend(series: list[dict[str, Any]], legend: list[str]) -> list[dict[str, Any]]:
    """Force a daily series to use the same model keys as the cost chart legend."""
    out: list[dict[str, Any]] = []
    fixed = [m for m in legend if m != "Other"]
    include_other = "Other" in legend
    for point in series:
        aligned: dict[str, Any] = {"date": point["date"], "total": 0.0}
        other = 0.0
        for m in fixed:
            v = float(point.get(m, 0) or 0)
            aligned[m] = round(v, 4)
            aligned["total"] += v
        for key, raw in point.items():
            if key in {"date", "total"} or key in fixed or key == "Other":
                continue
            other += float(raw or 0)
        if include_other:
            other += float(point.get("Other") or 0)
            aligned["Other"] = round(other, 4)
            aligned["total"] += other
        aligned["total"] = round(float(aligned["total"]), 4)
        out.append(aligned)
    return out


async def usage_summary(*, tenant_id: UUID | None, platform: bool) -> dict[str, Any]:
    from app.models.usage_event import UsageEvent
    from app.models.tenant import Tenant

    async with AsyncSessionLocal() as db:
        since = datetime.now(timezone.utc) - timedelta(days=_CHART_DAYS)
        q = select(UsageEvent).where(UsageEvent.created_at >= since)
        if not platform and tenant_id:
            q = q.where(UsageEvent.tenant_id == tenant_id)
        q = q.order_by(UsageEvent.created_at.desc())
        rows = list((await db.execute(q)).scalars().all())

        tenant_ids = {r.tenant_id for r in rows if r.tenant_id}
        names: dict[UUID, str] = {}
        if tenant_ids:
            trows = await db.execute(select(Tenant.id, Tenant.name).where(Tenant.id.in_(tenant_ids)))
            names = {row.id: row.name for row in trows.all()}

    totals = {
        "calls": len(rows),
        "failed_calls": sum(1 for r in rows if not r.success),
        "prompt_tokens": sum(int(r.prompt_tokens or 0) for r in rows),
        "completion_tokens": sum(int(r.completion_tokens or 0) for r in rows),
        "total_tokens": sum(int(r.total_tokens or 0) for r in rows),
        "credits": round(sum(float(r.credits or 0) for r in rows), 2),
        "cost_usd": round(sum(effective_cost_usd(r) for r in rows), 4),
    }

    def _bucket(key_fn):
        acc: dict[str, dict[str, Any]] = {}
        for r in rows:
            key = key_fn(r) or "unknown"
            slot = acc.setdefault(
                key,
                {"name": key, "calls": 0, "tokens": 0, "credits": 0.0, "cost_usd": 0.0, "failed": 0},
            )
            slot["calls"] += 1
            slot["tokens"] += int(r.total_tokens or 0)
            slot["credits"] += float(r.credits or 0)
            slot["cost_usd"] += effective_cost_usd(r)
            if not r.success:
                slot["failed"] += 1
        out = []
        for slot in acc.values():
            slot["credits"] = round(slot["credits"], 2)
            slot["cost_usd"] = round(slot["cost_usd"], 4)
            out.append(slot)
        out.sort(key=lambda x: x["cost_usd"], reverse=True)
        return out

    recent = []
    for r in rows[:120]:
        row_cost = effective_cost_usd(r)
        recent.append(
            {
                "id": str(r.id),
                "provider": r.provider,
                "model": r.model,
                "operation": r.operation,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "credits": float(r.credits or 0),
                "cost_usd": row_cost,
                "cost_estimated": row_cost > 0 and float(r.cost_usd or 0) <= 0 and is_byteplus_seedance_row(r),
                "success": r.success,
                "error": r.error,
                "client": names.get(r.tenant_id) if r.tenant_id else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )

    daily_cost, chart_models = _build_daily_series(rows, value_fn=effective_cost_usd)
    daily_requests_raw, _ = _build_daily_series(rows, value_fn=lambda r: 1.0)
    daily_requests = _align_series_to_legend(daily_requests_raw, chart_models)

    return {
        "totals": totals,
        "by_provider": _bucket(lambda r: r.provider),
        "by_model": _bucket(lambda r: r.model or r.provider),
        "seedance": _build_seedance_summary(rows, tenant_names=names),
        "recent": recent,
        "daily_cost": daily_cost,
        "daily_requests": daily_requests,
        "chart_models": chart_models,
        "period_days": _CHART_DAYS,
    }
