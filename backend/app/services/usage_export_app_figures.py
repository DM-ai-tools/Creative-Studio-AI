"""Excel sheets that carry the *same figures* as the Usage & costs page.

Every number here comes from ``usage_tracker.usage_summary`` (the function that
feeds the page), run over the exact same date range with the row caps lifted.
Nothing is re-derived, so the spreadsheet and the screen cannot disagree.

``Work by user`` is the one extra table: plain event counts per person
(images, video clips, voice-overs, text/AI calls, scrapes, failures).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.usage_tracker import (
    effective_cost_usd,
    fetch_usage_events,
    is_byteplus_seedance_row,
    usage_summary,
)

SheetSpec = tuple[str, list[list[Any]]]

_LINK_HEADERS = {"Video link", "Library link", "Open file", "Library"}


def _text_tokens(totals: dict[str, Any]) -> int:
    return max(0, int(totals.get("total_tokens") or 0) - int(totals.get("video_tokens") or 0))


def _media_spend(usage: dict[str, Any], name: str) -> float:
    for row in usage.get("by_media_type") or []:
        if str(row.get("name", "")).lower() == name.lower():
            return float(row.get("cost_usd") or 0)
    return 0.0


def _work_mode(row: Any) -> str:
    """Classify one usage event into the kind of work it represents."""
    op = (row.operation or "").lower()
    prov = (row.provider or "").lower()
    extra = row.extra or {}
    if "tts" in op:
        return "voice"
    if prov == "heygen":
        return "heygen"
    if is_byteplus_seedance_row(row) or "video" in op or extra.get("video_url"):
        return "video"
    if "image" in op and "analyze" not in op:
        return "image"
    if prov in {"firecrawl", "sociavault"} or "fetch_brand" in op or "fetch-brand" in op or "fetch_social" in op or "fetch-social" in op:
        return "scrape"
    return "text"


def _duration_seconds(row: Any) -> float:
    try:
        return float((row.extra or {}).get("duration_seconds") or 0)
    except (TypeError, ValueError):
        return 0.0


async def _work_by_user_rows(
    *,
    tenant_id: UUID | None,
    platform: bool,
    since: datetime,
    until: datetime | None,
    user_id: UUID | None,
) -> list[list[Any]]:
    rows = await fetch_usage_events(
        tenant_id=tenant_id, platform=platform, since=since, until=until, user_id=user_id
    )
    ids = {r.user_id for r in rows if r.user_id}
    labels: dict[UUID, str] = {}
    if ids:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(User.id, User.email, User.full_name).where(User.id.in_(ids)))
            for uid, email, name in res.all():
                labels[uid] = (name or "").strip() or (email or "").strip() or str(uid)

    acc: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "image": 0,
            "video": 0,
            "video_jobs": set(),
            "video_seconds": 0.0,
            "heygen": 0,
            "voice": 0,
            "text": 0,
            "scrape": 0,
            "failed": 0,
            "calls": 0,
            "cost": 0.0,
        }
    )
    for r in rows:
        label = labels.get(r.user_id, str(r.user_id)) if r.user_id else "Unknown user"
        slot = acc[label]
        slot["calls"] += 1
        slot["cost"] += effective_cost_usd(r)
        if not r.success:
            slot["failed"] += 1
            continue
        mode = _work_mode(r)
        slot[mode] += 1
        if mode == "video":
            slot["video_seconds"] += _duration_seconds(r)
            jid = str((r.extra or {}).get("job_id") or "").strip()
            if jid:
                slot["video_jobs"].add(jid)

    out: list[list[Any]] = [
        [
            "User",
            "Images generated",
            "Video clips generated",
            "Video jobs (distinct)",
            "Video seconds",
            "HeyGen videos",
            "Voice-overs",
            "Text / AI calls",
            "Scrapes",
            "Failed calls",
            "Total API calls",
            "Spend (USD)",
        ]
    ]
    for label, s in sorted(acc.items(), key=lambda x: -x[1]["cost"]):
        out.append(
            [
                label,
                s["image"],
                s["video"],
                len(s["video_jobs"]),
                round(s["video_seconds"], 1),
                s["heygen"],
                s["voice"],
                s["text"],
                s["scrape"],
                s["failed"],
                s["calls"],
                round(s["cost"], 4),
            ]
        )
    return out


def _daily_rows(rows: list[Any]) -> list[list[Any]]:
    acc: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "failed": 0, "cost": 0.0})
    for r in rows:
        if not r.created_at:
            continue
        day = r.created_at.astimezone(timezone.utc).date().isoformat()
        acc[day]["calls"] += 1
        acc[day]["cost"] += effective_cost_usd(r)
        if not r.success:
            acc[day]["failed"] += 1
    out: list[list[Any]] = [["Date (UTC)", "API calls", "Failed", "Spend (USD)"]]
    for day in sorted(acc):
        out.append([day, int(acc[day]["calls"]), int(acc[day]["failed"]), round(acc[day]["cost"], 4)])
    return out


async def build_app_figure_sheets(
    *,
    tenant_id: UUID | None,
    platform: bool,
    since: datetime,
    until: datetime | None,
    user_id: UUID | None,
    scope_label: str,
    period_label: str,
) -> list[SheetSpec]:
    """Return ``(sheet title, rows)`` pairs; the first row of each is the header."""
    usage = await usage_summary(
        tenant_id=tenant_id,
        platform=platform,
        user_id=user_id,
        since=since,
        until=until,
        recent_limit=None,
        clip_limit=None,
    )
    totals = usage["totals"]
    seed = usage["seedance"]

    figures: list[list[Any]] = [
        ["Metric (as shown on Usage & costs)", "Value"],
        ["Scope", scope_label],
        ["Period", period_label],
        ["From (UTC)", since.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")],
        ["To (UTC)", (until or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")],
        ["Total spend (USD)", totals["cost_usd"]],
        ["Image spend (USD)", round(_media_spend(usage, "Image"), 4)],
        ["Video spend (USD)", round(_media_spend(usage, "Video"), 4)],
        ["Other spend (USD) — text, voice, scrapes", round(totals["cost_usd"] - _media_spend(usage, "Image") - _media_spend(usage, "Video"), 4)],
        ["API calls", totals["calls"]],
        ["Failed calls", totals["failed_calls"]],
        ["Text tokens", _text_tokens(totals)],
        ["Video tokens", totals["video_tokens"]],
        ["Prompt tokens", totals["prompt_tokens"]],
        ["Completion tokens", totals["completion_tokens"]],
        ["Total tokens", totals["total_tokens"]],
        ["Credits", totals["credits"]],
        [""],
        ["Seedance / BytePlus video", ""],
        ["Successful clips", seed["successful_clips"]],
        ["Failed calls", seed["failed_calls"]],
        ["Completion tokens", seed["total_tokens"]],
        ["Est. spend (USD) — the figure shown", seed["cost_usd"]],
        ["Est. spend low (USD)", seed["cost_usd_low"]],
        ["Est. spend high (USD)", seed["cost_usd_high"]],
        [""],
        ["Note", seed["pricing_note"]],
    ]

    def _bucket_sheet(name_header: str, rows: list[dict[str, Any]]) -> list[list[Any]]:
        out: list[list[Any]] = [[name_header, "Calls", "Failed", "Tokens", "Credits", "Spend (USD)"]]
        for r in rows:
            out.append([r["name"], r["calls"], r["failed"], r["tokens"], r["credits"], r["cost_usd"]])
        return out

    by_user = [["User", "Calls", "Failed", "Tokens", "Credits", "Spend (USD)"]]
    for r in usage["by_user"]:
        by_user.append([r["name"], r["calls"], r["failed"], r["tokens"], r["credits"], r["cost_usd"]])

    seed_models = [["Model", "Clips", "Failed", "Tokens", "Est. spend (USD)", "Low (USD)", "High (USD)"]]
    for r in seed["by_model"]:
        seed_models.append(
            [r["model"], r["clips"], r["failed"], r["tokens"], r["cost_usd"], r["cost_usd_low"], r["cost_usd_high"]]
        )

    clips = [
        [
            "When (UTC)",
            "Client",
            "Task ID",
            "Model",
            "Resolution",
            "Duration (sec)",
            "Tokens",
            "Est. spend (USD)",
            "Low (USD)",
            "High (USD)",
            "Status",
            "Video link",
            "Library link",
        ]
    ]
    for c in seed["recent_clips"]:
        res = c.get("resolution") or ""
        if res and c.get("resolution_inferred"):
            res = f"{res}*"
        clips.append(
            [
                (c.get("created_at") or "")[:19].replace("T", " "),
                c.get("client") or "",
                c.get("task_id") or "",
                c.get("model") or "",
                res,
                c.get("duration_seconds") if c.get("duration_seconds") is not None else "",
                c.get("tokens") or 0,
                c["cost_usd"],
                c["cost_usd_low"],
                c["cost_usd_high"],
                "Recovered" if c.get("recovered") else "OK",
                c.get("media_url") or "",
                c.get("variant_url") or "",
            ]
        )
    clips.append([])
    clips.append(["* resolution worked out from tokens per second (older clip, not recorded)"])

    api_calls = [
        [
            "When (UTC)",
            "Client",
            "Provider",
            "Model",
            "Operation",
            "Tokens",
            "Credits",
            "Spend (USD)",
            "Spend estimated",
            "Status",
            "Error",
            "Open file",
            "Library",
        ]
    ]
    for c in usage["recent"]:
        api_calls.append(
            [
                (c.get("created_at") or "")[:19].replace("T", " "),
                c.get("client") or "",
                c.get("provider") or "",
                c.get("model") or "",
                c.get("operation") or "",
                c.get("total_tokens") or 0,
                c.get("credits") or 0,
                c["cost_usd"],
                "Yes" if c.get("cost_estimated") else "No",
                "OK" if c.get("success") else "Failed",
                (c.get("error") or "")[:300],
                c.get("media_url") or "",
                c.get("variant_url") or "",
            ]
        )

    work = await _work_by_user_rows(
        tenant_id=tenant_id, platform=platform, since=since, until=until, user_id=user_id
    )
    rows_for_daily = await fetch_usage_events(
        tenant_id=tenant_id, platform=platform, since=since, until=until, user_id=user_id
    )

    return [
        ("App figures", figures),
        ("Work by user", work),
        ("App - spend by user", by_user),
        ("App - by provider", _bucket_sheet("Provider", usage["by_provider"])),
        ("App - by model", _bucket_sheet("Model", usage["by_model"])),
        ("App - by media type", _bucket_sheet("Media type", usage["by_media_type"])),
        ("Seedance by model", seed_models),
        ("Seedance clips", clips),
        ("API calls (as in app)", api_calls),
        ("Daily", _daily_rows(rows_for_daily)),
    ]


def add_sheets(wb, specs: list[SheetSpec], *, start_index: int = 1) -> None:
    """Write the sheets into ``wb`` starting at ``start_index`` (after Read me)."""
    from app.services.usage_export_service import _add_hyperlinks, _autosize_columns

    for offset, (title, rows) in enumerate(specs):
        ws = wb.create_sheet(title=title[:31], index=start_index + offset)
        for row in rows:
            ws.append(row)
        for col in range(1, ws.max_column + 1):
            ws.cell(row=1, column=col).font = Font(bold=True)
        header = [str(c.value or "") for c in ws[1]]
        link_cols = [i + 1 for i, h in enumerate(header) if h in _LINK_HEADERS]
        if link_cols:
            _add_hyperlinks(ws, url_col_indices=link_cols)
        _autosize_columns(ws, max_width=44)
        if title == "App figures":
            ws.column_dimensions[get_column_letter(1)].width = 46
            ws.column_dimensions[get_column_letter(2)].width = 40
