"""Build Excel usage reports from usage_events."""

from __future__ import annotations

import io
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.asset import Asset
from app.models.brand import Brand
from app.models.brief import Brief
from app.models.tenant import Tenant
from app.models.user import User
from app.models.variant import Variant
from app.services.public_urls import (
    absolute_media_url,
    is_hosted_creative_file_url,
    media_urls_from_extra,
    normalize_stored_file_url,
    pick_image_and_video_links,
    public_app_origin,
    server_disk_path,
    variant_library_url,
)
from app.services.usage_tracker import (
    _display_model,
    _row_completion_tokens,
    effective_cost_usd,
    fetch_usage_events,
    is_byteplus_seedance_row,
    seedance_cost_detail,
)


MAX_EXPORT_ROWS = 25_000
MAX_RANGE_DAYS = 366

DETAIL_HEADERS = [
    "Date (UTC)",
    "User email",
    "User name",
    "Client / workspace",
    "Brand ID",
    "Brand name",
    "Category",
    "Media type",
    "Image link (for manager — click to open)",
    "Video link (for manager — click to open)",
    "File URL in app (/files/...)",
    "Server file location (local dev only)",
    "Creative library (open in app)",
    "Provider",
    "Model",
    "Operation",
    "Duration (sec)",
    "Prompt tokens",
    "Completion tokens",
    "Total tokens",
    "Cost (USD)",
    "Cost estimated",
    "Status",
    "Error",
    "Brief ID",
    "Variant ID",
    "Job ID",
    "Task ID",
    "Event ID",
]

# Column indices for summary rollups (0-based, must match DETAIL_HEADERS order)
_COL_STATUS = DETAIL_HEADERS.index("Status")
_COL_TOTAL_TOKENS = DETAIL_HEADERS.index("Total tokens")
_COL_COST = DETAIL_HEADERS.index("Cost (USD)")
_COL_MODEL = DETAIL_HEADERS.index("Model")
_COL_USER_EMAIL = DETAIL_HEADERS.index("User email")
_COL_BRAND_NAME = DETAIL_HEADERS.index("Brand name")
_COL_HYPERLINK_HEADERS = (
    "Image link (for manager — click to open)",
    "Video link (for manager — click to open)",
    "Creative library (open in app)",
)

CREATIVES_BY_BRAND_HEADERS = [
    "Date (UTC)",
    "User email",
    "User name",
    "Brand name",
    "Format",
    "Creative type",
    "Hook",
    "Image link (click to open)",
    "Video link (click to open)",
    "Open in Creative Studio",
    "Brief ID",
    "Variant ID",
]


def _uuid_or_none(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError, AttributeError):
        return None


def _load_creative_studio_job_metadata(
    job_ids: set[str],
    *,
    job_tenants: dict[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    """Recover report fields from persisted Creative Studio jobs.

    Usage events created by older builds sometimes contain only ``job_id``.  The
    persisted job is the authoritative source for the selected user/brand and
    for the final stitched output URL, so keep those values together here.
    """
    if not job_ids:
        return {}
    from app.services.creative_studio_job_service import _load_job_from_disk

    out: dict[str, dict[str, str]] = {}
    for jid in job_ids:
        if not jid:
            continue
        # Keep tenant exports isolated even though persisted jobs live below a
        # shared uploads root.
        job = _load_job_from_disk(jid, tenant_id=(job_tenants or {}).get(jid))
        if not job:
            continue
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        out[jid] = _job_meta_from_record(job)
    return out


def _job_meta_from_record(job: dict[str, Any]) -> dict[str, str]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    provider_task = (
        str(job.get("provider_task_id") or "").strip()
        or str(result.get("provider_task_id") or "").strip()
        or str(result.get("task_id") or "").strip()
    )
    return {
        "url": str(result.get("url") or "").strip(),
        "user_id": str(payload.get("user_id") or job.get("user_id") or "").strip(),
        "brand_id": str(payload.get("brand_id") or "").strip(),
        "brand_name": str(payload.get("brand_name") or "").strip(),
        "brief_id": str(payload.get("brief_id") or "").strip(),
        "media_mode": str(payload.get("media_mode") or result.get("media_mode") or "").strip(),
        "provider_task_id": provider_task,
    }


def _load_task_job_metadata(task_tenants: dict[str, str | None]) -> dict[str, dict[str, str]]:
    """Map BytePlus ``task_id`` (cgt-…) to persisted Creative Studio job payload."""
    if not task_tenants:
        return {}
    root = Path(settings.UPLOAD_DIR).resolve()
    if not root.is_dir():
        return {}
    out: dict[str, dict[str, str]] = {}

    def _scan_dir(jobs_dir: Path) -> None:
        if not jobs_dir.is_dir():
            return
        for path in jobs_dir.glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(job, dict):
                continue
            meta = _job_meta_from_record(job)
            tid = str(meta.get("provider_task_id") or "").strip()
            if tid and tid in task_tenants and tid not in out:
                out[tid] = meta

    for task_id, tenant_id in task_tenants.items():
        if task_id in out:
            continue
        if tenant_id:
            _scan_dir(root / str(tenant_id) / "creative-studio-jobs")
        else:
            for tenant_dir in sorted(root.iterdir()):
                if tenant_dir.is_dir():
                    _scan_dir(tenant_dir / "creative-studio-jobs")
                    if task_id in out:
                        break
    return out


def _job_urls(job_metadata: dict[str, dict[str, str]]) -> dict[str, str]:
    return {
        jid: str(meta.get("url") or "").strip()
        for jid, meta in job_metadata.items()
        if str(meta.get("url") or "").strip()
    }


def _stored_paths_from_extra(extra: dict | None, *, job_urls: dict[str, str]) -> list[str]:
    paths: list[str] = []
    for abs_u in media_urls_from_extra(extra):
        norm = normalize_stored_file_url(abs_u)
        if norm:
            paths.append(norm)
    jid = str((extra or {}).get("job_id") or "").strip()
    if jid and jid in job_urls:
        norm = normalize_stored_file_url(job_urls[jid])
        if norm:
            paths.append(norm)
    return paths


def _category(operation: str, provider: str) -> str:
    op = (operation or "").lower()
    prov = (provider or "").lower()
    if "analyze-reference-image" in op or "analyze_reference" in op:
        return "LLM / copy"
    if "creative_studio" in op or prov == "byteplus":
        return "Creative Studio"
    if op in {
        "generate_image",
        "hero_ai_image",
        "creative_studio_image",
        "creative_studio_character_portrait",
    } or ("image" in op and "analyze" not in op):
        return "Image generation"
    if op == "generate_video" or "video" in op:
        return "Video generation"
    if prov == "firecrawl" or "fetch_brand" in op:
        return "Brand scrape"
    if prov == "openrouter" or op.startswith("llm") or "chat" in op:
        return "LLM / copy"
    if prov == "heygen":
        return "HeyGen"
    if prov == "higgsfield":
        return "Higgsfield"
    if prov == "sociavault":
        return "Social scrape"
    if prov == "meta":
        return "Meta export"
    return "Other"


def _media_type(operation: str, provider: str, extra: dict | None) -> str:
    mt = str((extra or {}).get("media_type") or "").strip().lower()
    if mt in {"image", "video", "text"}:
        return mt.title()
    op = (operation or "").lower()
    if "analyze-reference-image" in op or "analyze_reference" in op:
        return "Text"
    if op == "generate_video" or (extra or {}).get("video_url"):
        return "Video"
    if op == "generate_image" or (extra or {}).get("image_url"):
        return "Image"
    if "video" in op:
        return "Video"
    if "image" in op:
        return "Image"
    if prov := (provider or "").lower():
        if prov == "byteplus" and "video" in op:
            return "Video"
    if op.startswith("llm") or "chat" in op or prov == "openrouter":
        return "Text"
    return ""


def parse_usage_date_range(
    *,
    days: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[datetime, datetime, str]:
    now = datetime.now(timezone.utc)
    if date_from and date_to:
        if date_to < date_from:
            raise ValueError("End date must be on or after start date")
        span = (date_to - date_from).days + 1
        if span > MAX_RANGE_DAYS:
            raise ValueError(f"Date range cannot exceed {MAX_RANGE_DAYS} days")
        since = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        until = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        label = f"{date_from.isoformat()}_{date_to.isoformat()}"
        return since, until, label
    period = max(1, min(int(days or 30), MAX_RANGE_DAYS))
    since = now - timedelta(days=period)
    until = now
    label = f"last_{period}_days"
    return since, until, label


def _detail_row(
    row: Any,
    *,
    users: dict[UUID, User],
    tenants: dict[UUID, str],
    brands: dict[UUID, str],
    brief_brands: dict[UUID, UUID] | None = None,
    variant_brands: dict[UUID, UUID] | None = None,
    variant_asset_urls: dict[UUID, list[str]] | None = None,
    job_metadata: dict[str, dict[str, str]] | None = None,
    file_url_to_variant: dict[str, UUID] | None = None,
    file_url_to_brand: dict[str, UUID] | None = None,
    file_url_to_user: dict[str, UUID] | None = None,
    pipeline_file_to_variant: dict[str, UUID] | None = None,
    variant_pipeline_media: dict[UUID, dict[str, str]] | None = None,
) -> list[Any]:
    extra = row.extra or {}
    job_id_str = str(extra.get("job_id") or "").strip()
    job_meta = (job_metadata or {}).get(job_id_str) or {}
    job_url = str(job_meta.get("url") or "").strip()
    job_media_urls = {job_id_str: job_url} if job_id_str and job_url else {}
    brief_id_str = str(extra.get("brief_id") or job_meta.get("brief_id") or "").strip()
    brand_id_str = str(extra.get("brand_id") or job_meta.get("brand_id") or "").strip()
    brand_name = str(extra.get("brand_name") or job_meta.get("brand_name") or "").strip()

    cost = effective_cost_usd(row)
    estimated = cost > 0 and float(row.cost_usd or 0) <= 0 and is_byteplus_seedance_row(row)
    urls = media_urls_from_extra(extra)
    # A provider row can point at an intermediate segment.  Put the persisted
    # Creative Studio result first so a manager opens the final stitched asset.
    final_job_url = absolute_media_url(job_url)
    if final_job_url:
        urls = [final_job_url, *[url for url in urls if url != final_job_url]]
    variant_id_str = str(extra.get("variant_id") or "").strip()
    stored_paths = _stored_paths_from_extra(extra, job_urls=job_media_urls or {})
    stored_file = stored_paths[0] if stored_paths else ""
    if not variant_id_str and file_url_to_variant:
        for path in stored_paths:
            vid = file_url_to_variant.get(path)
            if vid:
                variant_id_str = str(vid)
                break
    if not variant_id_str and stored_file and pipeline_file_to_variant:
        vid = pipeline_file_to_variant.get(stored_file)
        if vid:
            variant_id_str = str(vid)

    # Resolve the brand only after asset/pipeline lookups have had a chance to
    # recover a missing variant.  This order is important for historical rows.
    brand_uuid = _uuid_or_none(brand_id_str)
    if not brand_uuid and brief_id_str and brief_brands:
        brand_uuid = brief_brands.get(_uuid_or_none(brief_id_str))
    if not brand_uuid and variant_id_str and variant_brands:
        brand_uuid = variant_brands.get(_uuid_or_none(variant_id_str))
    if not brand_uuid and file_url_to_brand:
        for path in stored_paths:
            if file_url_to_brand.get(path):
                brand_uuid = file_url_to_brand[path]
                break
    if brand_uuid:
        brand_id_str = str(brand_uuid)
        if not brand_name:
            brand_name = brands.get(brand_uuid, "")

    user_uuid = row.user_id or _uuid_or_none(job_meta.get("user_id"))
    if not user_uuid and file_url_to_user:
        for path in stored_paths:
            if file_url_to_user.get(path):
                user_uuid = file_url_to_user[path]
                break
    user = users.get(user_uuid) if user_uuid else None
    if not urls and variant_asset_urls and variant_id_str:
        try:
            urls = list(variant_asset_urls.get(UUID(variant_id_str)) or [])
        except ValueError:
            pass
    if not stored_file and urls:
        stored_file = normalize_stored_file_url(urls[0])
    if not urls and stored_file:
        urls = [absolute_media_url(stored_file)]
    image_link, video_link = pick_image_and_video_links(
        urls,
        extra=extra,
        operation=row.operation or "",
        provider=row.provider or "",
    )
    if variant_id_str and variant_pipeline_media:
        try:
            pipe = variant_pipeline_media.get(UUID(variant_id_str)) or {}
            if not image_link and pipe.get("image") and is_hosted_creative_file_url(pipe["image"]):
                image_link = pipe["image"]
            if not video_link and pipe.get("video") and is_hosted_creative_file_url(pipe["video"]):
                video_link = pipe["video"]
        except ValueError:
            pass
    media_type = _media_type(row.operation, row.provider, extra)
    if media_type == "Image":
        video_link = ""
    elif media_type == "Video":
        image_link = ""
    elif media_type == "Text":
        image_link = ""
        video_link = ""
    if not brand_name and media_type in {"Image", "Video"}:
        brand_name = "Legacy – brand unavailable"
    disk_path = ""
    if not settings.is_production and stored_file:
        disk_path = server_disk_path(stored_file)
    library_link = variant_library_url(variant_id_str) if variant_id_str else ""
    prompt_tok = int(row.prompt_tokens or 0)
    completion_tok = int(row.completion_tokens or 0)
    total_tok = int(row.total_tokens or 0)
    if total_tok and not completion_tok and is_byteplus_seedance_row(row):
        completion_tok = total_tok if not prompt_tok else max(0, total_tok - prompt_tok)
    task_id = extra.get("task_id") if isinstance(extra.get("task_id"), str) else ""
    if not task_id and isinstance(extra, dict):
        task_id = str(extra.get("task_id") or "")

    duration = extra.get("duration_seconds")
    try:
        duration_val = float(duration) if duration is not None else ""
    except (TypeError, ValueError):
        duration_val = ""

    created = row.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if row.created_at else ""

    return [
        created,
        (user.email if user else ""),
        (user.full_name if user else ""),
        tenants.get(row.tenant_id, "") if row.tenant_id else "",
        brand_id_str,
        brand_name,
        _category(row.operation, row.provider),
        media_type,
        image_link,
        video_link,
        stored_file,
        disk_path,
        library_link,
        row.provider,
        _display_model(row.model, row.provider),
        row.operation,
        duration_val,
        prompt_tok,
        completion_tok,
        total_tok or (prompt_tok + completion_tok),
        round(cost, 6),
        "Yes" if estimated else "No",
        "Success" if row.success else "Failed",
        (row.error or "")[:500] if row.error else "",
        brief_id_str,
        variant_id_str,
        job_id_str,
        task_id,
        str(row.id),
    ]


def _write_sheet_headers(ws, headers: list[str]) -> None:
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True)


def _autosize_columns(ws, max_width: int = 48) -> None:
    for col_idx, column_cells in enumerate(ws.columns, 1):
        length = max(len(str(c.value or "")) for c in column_cells)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(length + 2, 10), max_width)


def _add_hyperlinks(ws, url_col_indices: list[int], start_row: int = 2) -> None:
    link_font = Font(color="0563C1", underline="single")
    for row_idx in range(start_row, ws.max_row + 1):
        for col_idx in url_col_indices:
            cell = ws.cell(row=row_idx, column=col_idx)
            val = str(cell.value or "").strip()
            if val.startswith("http"):
                cell.hyperlink = val
                cell.font = link_font


def _summary_rows(
    detail_rows: list[list[Any]],
    *,
    group_col: int,
    label: str,
) -> list[list[Any]]:
    acc: dict[str, dict[str, Any]] = {}
    for row in detail_rows:
        key = str(row[group_col] or "(blank)")
        slot = acc.setdefault(key, {"calls": 0, "failed": 0, "cost": 0.0, "tokens": 0})
        slot["calls"] += 1
        if row[_COL_STATUS] == "Failed":
            slot["failed"] += 1
        try:
            slot["cost"] += float(row[_COL_COST] or 0)
        except (TypeError, ValueError):
            pass
        slot["tokens"] += int(row[_COL_TOTAL_TOKENS] or 0)
    out = [[label, "Calls", "Failed", "Total tokens", "Cost (USD)"]]
    for key, slot in sorted(acc.items(), key=lambda x: x[1]["cost"], reverse=True):
        out.append([key, slot["calls"], slot["failed"], slot["tokens"], round(slot["cost"], 4)])
    return out


def _readme_sheet_rows() -> list[list[str]]:
    origin = public_app_origin()
    prod = settings.is_production
    return [
        ["Usage report — for your reporting manager"],
        [""],
        ["How to use", "Log in as admin → Usage & costs → Download Excel → email this file."],
        [
            "For client / manager reports",
            "Use the tab «Creatives by brand (manager)» — one row per finished image or video, grouped by brand with working /files/ links.",
        ],
        ["Image link", f"Blue hyperlink — opens the still in a browser ({origin}/files/...)."],
        ["Video link", f"Blue hyperlink — opens the video in a browser ({origin}/files/...)."],
        ["Creative library", "Opens that saved creative inside the app (variants page)."],
        [""],
        ["Usage detail tab", "Technical API log (includes LLM calls). Ignore rows with empty image/video cells."],
        ["Production (creativestudio.tools)", "Send the «Creatives by brand» tab; disk path is blank on purpose."],
        ["Local development", "Disk path column shows where the file sits under backend/uploads on your PC."],
        [""],
        ["Empty image/video cell?", "That row was text/LLM only, or the file was not recorded yet. Re-export after new work."],
        ["Tip", "Save Creative Studio outputs to Creative library so variant links fill in for managers."],
    ]


def _pipeline_block_url(block: Any, *, prefer_video: bool = False) -> str:
    if not isinstance(block, dict):
        return ""
    if str(block.get("status") or "").lower() in {"skipped", "failed"} and not block.get("url"):
        return ""
    candidates: list[str] = []
    for key in ("url", "video_url", "image_url", "file_url", "output_url", "remote_url"):
        raw = block.get(key)
        if raw:
            candidates.append(absolute_media_url(str(raw)))
    op = "generate_video" if prefer_video else "generate_image"
    img, vid = pick_image_and_video_links(candidates, operation=op)
    return vid if prefer_video else img


def _pipeline_media_from_variant(
    params: dict | None,
    *,
    asset_urls: list[str] | None = None,
    usage_image: str = "",
    usage_video: str = "",
) -> tuple[str, str]:
    pipe = (params or {}).get("pipeline") if isinstance(params, dict) else None
    img = _pipeline_block_url(pipe.get("image") if isinstance(pipe, dict) else None)
    vid = _pipeline_block_url(pipe.get("video") if isinstance(pipe, dict) else None, prefer_video=True)
    if not img and not vid and isinstance(pipe, dict):
        # Some builds store the final file on the video step without nested url keys.
        top = pick_image_and_video_links(
            [absolute_media_url(str(pipe.get("url") or ""))],
            operation="generate_video",
        )
        vid = top[1] or top[0]
    if asset_urls:
        a_img, a_vid = pick_image_and_video_links(
            asset_urls,
            operation="generate_video",
            provider="heygen",
        )
        if not img and a_img:
            img = a_img
        if not vid and a_vid:
            vid = a_vid
    if usage_image and is_hosted_creative_file_url(usage_image):
        img = img or usage_image
    if usage_video and is_hosted_creative_file_url(usage_video):
        vid = vid or usage_video
    if img and not is_hosted_creative_file_url(img):
        img = ""
    if vid and not is_hosted_creative_file_url(vid):
        vid = ""
    return img, vid


def _pipeline_step_done(params: dict | None, step: str, fmt: str) -> bool:
    pipe = (params or {}).get("pipeline") if isinstance(params, dict) else None
    if not isinstance(pipe, dict):
        return False
    block = pipe.get(step)
    if not isinstance(block, dict):
        return False
    st = str(block.get("status") or "").lower()
    if st in {"skipped", "failed", "error"}:
        return False
    if st in {"done", "complete", "completed", "ready", "mock"}:
        return True
    if block.get("url") or block.get("video_url") or block.get("image_url"):
        return True
    if step == "video" and fmt in {"reel", "video"} and st not in {"", "pending", "running"}:
        return st == "done"
    return False


def _variant_delivery_flags(
    variant: Any,
    img: str,
    vid: str,
) -> tuple[bool, bool]:
    """Count deliverables even when hosted /files/ URLs are missing from exports."""
    fmt = (variant.format or "").lower()
    status = str(getattr(variant, "status", "") or "").upper()
    library_ready = status in {"READY", "APPROVED", "EXPORTED"}
    params = variant.generation_params if isinstance(variant.generation_params, dict) else {}
    has_img = bool(img) or _pipeline_step_done(params, "image", fmt)
    has_vid = bool(vid) or _pipeline_step_done(params, "video", fmt)
    if fmt in {"static", "carousel"} and not has_img:
        has_img = _pipeline_step_done(params, "image", fmt)
    if fmt in {"reel", "video"} and not has_vid:
        has_vid = _pipeline_step_done(params, "video", fmt)
    # Match Creative library tiles: READY/APPROVED static rows count as delivered images.
    if library_ready:
        if fmt in {"static", "carousel"}:
            has_img = True
        elif fmt in {"reel", "video"}:
            has_vid = True
        elif not has_img and not has_vid:
            has_img = True
    return has_img, has_vid


async def _asset_creator_email_by_variant(variant_ids: set[UUID]) -> dict[UUID, str]:
    if not variant_ids:
        return {}
    out: dict[UUID, str] = {}
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Asset.variant_id, User.email)
            .join(User, Asset.created_by == User.id)
            .where(Asset.variant_id.in_(variant_ids), Asset.created_by.is_not(None))
            .order_by(Asset.created_at.desc())
        )
        for variant_id, email in rows.all():
            if variant_id and variant_id not in out and email:
                clean = _sanitize_contributor_email(str(email))
                if clean:
                    out[variant_id] = clean
    return out


_LEGACY_BRAND_LABELS = frozenset(
    {
        "legacy – brand unavailable",
        "legacy - brand unavailable",
        "no brand",
        "(no brand)",
    }
)

_NO_BRAND_BUCKET = "(no brand)"
_MAX_HOOK_SAMPLES = 8
_HOOK_SAMPLE_LEN = 100


def _is_placeholder_brand(name: str) -> bool:
    raw = (name or "").strip()
    if not raw:
        return True
    return raw.lower() in _LEGACY_BRAND_LABELS


def _normalize_brand_bucket(name: str) -> str:
    """Single rollup key for missing/placeholder brand labels."""
    if _is_placeholder_brand(name):
        return _NO_BRAND_BUCKET
    return (name or "").strip()


def _brand_summary_rollup_key(*, db_brand_label: str, display_brand: str) -> str:
    """One By brand row per real client — DB brand wins over hook-inferred label."""
    db = (db_brand_label or "").strip()
    if db and not _is_placeholder_brand(db):
        return _normalize_brand_bucket(db)
    return _normalize_brand_bucket((display_brand or "").strip())


def _sanitize_contributor_email(email: str) -> str:
    e = (email or "").strip()
    if not e or _is_automation_service_email(e):
        return ""
    return e


def _brand_hints_from_params(params: dict | None) -> str:
    if not isinstance(params, dict):
        return ""
    chunks: list[str] = []
    for key in ("brand_name", "client_name", "brand", "client"):
        raw = params.get(key)
        if raw:
            chunks.append(str(raw))
    return " ".join(chunks)


def _infer_brand_from_text(text: str, known_brands: list[str]) -> str:
    hay = (text or "").strip()
    if len(hay) < 3 or not known_brands:
        return ""
    hay_lower = hay.lower()
    for brand in sorted({b.strip() for b in known_brands if b and b.strip()}, key=len, reverse=True):
        if len(brand) < 3:
            continue
        if brand.lower() in hay_lower:
            return brand
    return ""


def _manager_brand_from_context(
    *,
    brand_name: str = "",
    hook: str = "",
    brief_title: str = "",
    product_name: str = "",
    known_brands: list[str],
) -> tuple[str, bool]:
    """Return display brand for managers; bool = True when inferred from hook/brief text."""
    raw = (brand_name or "").strip()
    if raw and not _is_placeholder_brand(raw):
        return raw, False
    for text in (hook, brief_title, product_name):
        hit = _infer_brand_from_text(text, known_brands)
        if hit:
            return hit, True
    if raw and not _is_placeholder_brand(raw):
        return raw, False
    return _NO_BRAND_BUCKET, False


def _hook_sample_key(hook: str) -> str:
    return (hook or "").strip()[: _HOOK_SAMPLE_LEN]


async def _load_known_brand_names(
    *,
    tenant_id: UUID | None,
    platform: bool,
) -> list[str]:
    async with AsyncSessionLocal() as db:
        q = select(Brand.name).where(Brand.name.is_not(None))
        if not platform and tenant_id:
            q = q.where(Brand.tenant_id == tenant_id)
        rows = await db.execute(q)
        return [str(r[0]).strip() for r in rows.all() if str(r[0] or "").strip()]


async def _usage_contributor_maps(
    *,
    tenant_id: UUID | None,
    platform: bool,
    since: datetime,
    until: datetime,
) -> tuple[dict[UUID, set[str]], dict[UUID, set[str]], dict[UUID, str]]:
    """Map variant/brief -> contributor emails from successful usage in the period."""
    from app.models.usage_event import UsageEvent

    variant_emails: dict[UUID, set[str]] = {}
    brief_emails: dict[UUID, set[str]] = {}
    user_ids: set[UUID] = set()
    async with AsyncSessionLocal() as db:
        q = (
            select(UsageEvent.user_id, UsageEvent.extra)
            .where(UsageEvent.created_at >= since)
            .where(UsageEvent.created_at <= until)
            .where(UsageEvent.success.is_(True))
            .where(UsageEvent.user_id.is_not(None))
        )
        if not platform and tenant_id:
            q = q.where(UsageEvent.tenant_id == tenant_id)
        rows = (await db.execute(q)).all()
    for user_id, extra in rows:
        if not user_id:
            continue
        user_ids.add(user_id)
        ex = extra or {}
        vid = _uuid_or_none(ex.get("variant_id"))
        brief_id = _uuid_or_none(ex.get("brief_id"))
        if vid:
            variant_emails.setdefault(vid, set()).add(user_id)
        if brief_id:
            brief_emails.setdefault(brief_id, set()).add(user_id)
    emails_by_user: dict[UUID, str] = {}
    if user_ids:
        async with AsyncSessionLocal() as db:
            urows = await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))
            emails_by_user = {row.id: (row.email or "") for row in urows.all()}
    variant_out: dict[UUID, set[str]] = {}
    for vid, uids in variant_emails.items():
        variant_out[vid] = {
            emails_by_user[uid]
            for uid in uids
            if uid in emails_by_user and _sanitize_contributor_email(emails_by_user[uid])
        }
    brief_out: dict[UUID, set[str]] = {}
    for bid, uids in brief_emails.items():
        brief_out[bid] = {
            emails_by_user[uid]
            for uid in uids
            if uid in emails_by_user and _sanitize_contributor_email(emails_by_user[uid])
        }
    return variant_out, brief_out, emails_by_user


def _resolve_brand_label(
    *,
    brand_name: str = "",
    brand_id: UUID | None = None,
    brief_id: UUID | None = None,
    brands: dict[UUID, str],
    brief_brands: dict[UUID, UUID],
) -> str:
    raw = (brand_name or "").strip()
    if raw and not _is_placeholder_brand(raw):
        return raw
    if brand_id and brand_id in brands:
        return brands[brand_id]
    if brief_id and brief_id in brief_brands:
        bid = brief_brands[brief_id]
        if bid in brands:
            return brands[bid]
    return ""


def _is_gemini_omni_video_row(ev: Any) -> bool:
    prov = (getattr(ev, "provider", "") or "").lower()
    model = (getattr(ev, "model", "") or "").lower()
    op = (getattr(ev, "operation", "") or "").lower()
    return prov == "google" and "omni" in model and op == "video_generation"


def _is_automation_service_email(email: str) -> bool:
    """Shared login used by Seedance/Omni workers — not a person on By user."""
    e = (email or "").strip().lower()
    if not e:
        return False
    return "seedance" in e and "creativestudio.tools" in e


def _usage_has_successful_media_output(ev: Any, *, job_meta: dict[str, str] | None = None) -> bool:
    """Count API deliverables when output URL exists, or Seedance billed successfully (dashboard parity)."""
    if not getattr(ev, "success", False):
        return False
    ex = getattr(ev, "extra", None) or {}
    if media_urls_from_extra(ex):
        return True
    if ex.get("video_url") or ex.get("image_url"):
        return True
    raw_urls = ex.get("output_urls")
    if isinstance(raw_urls, list) and any(str(u or "").strip() for u in raw_urls):
        return True
    if job_meta and str(job_meta.get("url") or "").strip():
        return True
    if is_byteplus_seedance_row(ev) or _is_gemini_omni_video_row(ev):
        task_id = str(ex.get("task_id") or "").strip()
        if task_id and _row_completion_tokens(ev) > 0:
            return True
    return False


def _usage_delivery_dedup_key(ev: Any) -> str:
    ex = getattr(ev, "extra", None) or {}
    for key in ("job_id", "task_id", "interaction_id"):
        raw = str(ex.get(key) or "").strip()
        if raw:
            return f"{key}:{raw}"
    eid = getattr(ev, "id", None)
    return f"event:{eid}" if eid else f"event:{id(ev)}"


def _usage_media_cost_dedup_key(ev: Any) -> str:
    """One media charge per clip/image — do not collapse whole chat jobs onto one image."""
    ex = getattr(ev, "extra", None) or {}
    vid = str(ex.get("variant_id") or "").strip()
    if vid:
        return f"variant:{vid}:cost"
    kind = _usage_delivery_kind(ev)
    if kind == "image":
        urls = media_urls_from_extra(ex)
        if urls:
            norm = normalize_stored_file_url(urls[0]) or urls[0]
            return f"image:{norm}"
        task = str(ex.get("task_id") or "").strip()
        if task:
            return f"task:{task}:image"
        eid = getattr(ev, "id", None)
        return f"event:{eid}:image" if eid else f"event:{id(ev)}:image"
    return _usage_delivery_dedup_key(ev)


def _resolve_usage_brand_key(
    ev: Any,
    *,
    job_meta: dict[str, str] | None,
    brands: dict[UUID, str],
    brief_brands: dict[UUID, UUID],
    variant_brands: dict[UUID, UUID],
    known_brands: list[str],
) -> str:
    ex = ev.extra or {}
    bname = _resolve_brand_label(
        brand_name=str(ex.get("brand_name") or (job_meta or {}).get("brand_name") or ""),
        brand_id=_uuid_or_none(ex.get("brand_id") or (job_meta or {}).get("brand_id")),
        brief_id=_uuid_or_none(ex.get("brief_id") or (job_meta or {}).get("brief_id")),
        brands=brands,
        brief_brands=brief_brands,
    )
    vid = _uuid_or_none(ex.get("variant_id"))
    if not bname and vid and vid in variant_brands:
        bid = variant_brands[vid]
        if bid in brands:
            bname = brands[bid]
    brief_id = _uuid_or_none(ex.get("brief_id") or (job_meta or {}).get("brief_id"))
    if not bname and brief_id and brief_id in brief_brands:
        bid = brief_brands[brief_id]
        if bid in brands:
            bname = brands[bid]
    hook_hint = str(
        ex.get("hook") or ex.get("prompt") or ex.get("title") or (job_meta or {}).get("brand_name") or ""
    )[:120]
    resolved, _ = _manager_brand_from_context(
        brand_name=bname,
        hook=hook_hint,
        known_brands=known_brands,
    )
    return _normalize_brand_bucket(resolved or bname)


def _resolve_usage_actor(
    ev: Any,
    *,
    users: dict[UUID, User],
    job_metadata: dict[str, dict[str, str]],
    task_job_metadata: dict[str, dict[str, str]] | None = None,
    brief_owners: dict[UUID, UUID] | None = None,
) -> tuple[str, str]:
    """Prefer human from CS job / BytePlus task / brief owner — not Seedance service login."""
    ex = ev.extra or {}
    jid = str(ex.get("job_id") or "").strip()
    job_meta = job_metadata.get(jid) if jid else None
    task_id = str(ex.get("task_id") or "").strip()
    if not job_meta and task_id and task_job_metadata:
        job_meta = task_job_metadata.get(task_id)

    def _user_from_meta(meta: dict[str, str] | None) -> tuple[str, str]:
        if not meta:
            return "", ""
        uid = _uuid_or_none(meta.get("user_id"))
        if uid and uid in users:
            u = users[uid]
            email = (u.email or "").strip()
            if email and not _is_automation_service_email(email):
                return email, (u.full_name or "").strip()
        return "", ""

    email, name = _user_from_meta(job_meta)
    if email:
        return email, name
    if jid and jid in job_metadata:
        email, name = _user_from_meta(job_metadata[jid])
        if email:
            return email, name

    brief_id = _uuid_or_none(ex.get("brief_id") or (job_meta or {}).get("brief_id"))
    if brief_id and brief_owners and brief_id in brief_owners:
        uid = brief_owners[brief_id]
        if uid in users:
            u = users[uid]
            email = (u.email or "").strip()
            if email and not _is_automation_service_email(email):
                return email, (u.full_name or "").strip()

    if ev.user_id and ev.user_id in users:
        u = users[ev.user_id]
        email = (u.email or "").strip()
        if email and not _is_automation_service_email(email):
            return email, (u.full_name or "").strip()
    return "", ""


def _resolve_event_job_meta(
    ev: Any,
    *,
    job_metadata: dict[str, dict[str, str]],
    task_job_metadata: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    ex = ev.extra or {}
    jid = str(ex.get("job_id") or "").strip()
    if jid and jid in job_metadata:
        return job_metadata[jid]
    task_id = str(ex.get("task_id") or "").strip()
    if task_id and task_id in task_job_metadata:
        return task_job_metadata[task_id]
    return None


def _manager_media_cost_usd(ev: Any, *, job_meta: dict[str, str] | None = None) -> float:
    """By brand: logged media cost only — same Seedance token/duration rules as usage dashboard."""
    if not getattr(ev, "success", False):
        return 0.0
    if is_byteplus_seedance_row(ev) or _is_gemini_omni_video_row(ev):
        if not _usage_has_successful_media_output(ev, job_meta=job_meta):
            return 0.0
        stored = float(getattr(ev, "cost_usd", 0) or 0)
        if stored > 0:
            return stored
        if is_byteplus_seedance_row(ev):
            detail = seedance_cost_detail(ev)
            return float(detail["mid"]) if detail else 0.0
        return _usage_media_cost_usd(ev)
    stored = float(getattr(ev, "cost_usd", 0) or 0)
    if stored > 0:
        return stored
    if _usage_delivery_kind(ev) == "image":
        from app.services.usage_tracker import estimate_media_cost

        cost, _ = estimate_media_cost(
            provider=str(getattr(ev, "provider", "") or ""),
            model=str(getattr(ev, "model", "") or ""),
        )
        if cost > 0:
            return cost
    media = _usage_media_cost_usd(ev)
    return media if media > 0 else 0.0


def _usage_media_cost_usd(ev: Any) -> float:
    """USD to show on By brand — image/video generation only (not LLM / scrape / chat)."""
    if not getattr(ev, "success", False):
        return 0.0
    if _usage_delivery_kind(ev):
        return effective_cost_usd(ev)
    cat = _category(
        getattr(ev, "operation", "") or "",
        getattr(ev, "provider", "") or "",
    )
    if cat in {"Image generation", "Video generation", "HeyGen", "Higgsfield"}:
        return effective_cost_usd(ev)
    op = (getattr(ev, "operation", "") or "").lower()
    if cat == "Creative Studio" and any(k in op for k in ("video", "image", "broll", "seedance")):
        return effective_cost_usd(ev)
    if is_byteplus_seedance_row(ev) or _is_gemini_omni_video_row(ev):
        return effective_cost_usd(ev)
    return 0.0


def _usage_delivery_kind(ev: Any) -> str | None:
    """Successful image/video generation (excludes LLM-only rows)."""
    if not getattr(ev, "success", False):
        return None
    op = (getattr(ev, "operation", None) or "").lower()
    if "analyze-reference-image" in op or "analyze_reference" in op:
        return None
    if op.startswith("llm") or "chat_completion" in op or op in {"chat", "completion"}:
        return None
    ex = getattr(ev, "extra", None) or {}
    mt = _media_type(getattr(ev, "operation", "") or "", getattr(ev, "provider", "") or "", ex)
    if mt == "Image":
        return "image"
    if mt == "Video":
        return "video"
    if is_byteplus_seedance_row(ev) or _is_gemini_omni_video_row(ev):
        if _usage_has_successful_media_output(ev):
            return "video"
        task_id = str(ex.get("task_id") or "").strip()
        if task_id and _row_completion_tokens(ev) > 0:
            return "video"
        return None
    return None


def _brief_usage_video_fallback(
    variant: Any,
    brief_video_events: dict[UUID, list[tuple[datetime, str]]],
) -> str:
    events = brief_video_events.get(variant.brief_id) or []
    if not events or not variant.created_at:
        return ""
    best_url = ""
    best_delta: float | None = None
    created = variant.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    for ts, url in events:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = abs((created - ts).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_url = url
    if best_url and best_delta is not None and best_delta <= 7200:
        return best_url
    return ""


async def _brief_usage_video_events(
    *,
    tenant_id: UUID | None,
    platform: bool,
    since: datetime,
    until: datetime,
) -> dict[UUID, list[tuple[datetime, str]]]:
    from app.models.usage_event import UsageEvent

    out: dict[UUID, list[tuple[datetime, str]]] = {}
    async with AsyncSessionLocal() as db:
        q = select(UsageEvent).where(UsageEvent.created_at >= since).where(UsageEvent.created_at <= until)
        if not platform and tenant_id:
            q = q.where(UsageEvent.tenant_id == tenant_id)
        q = q.where(UsageEvent.success.is_(True))
        events = list((await db.execute(q)).scalars().all())
    for ev in events:
        op = (ev.operation or "").lower()
        if op != "generate_video" and "generate_video" not in op and not is_byteplus_seedance_row(ev):
            continue
        ex = ev.extra or {}
        brief_raw = ex.get("brief_id")
        if not brief_raw:
            continue
        try:
            brief_uuid = UUID(str(brief_raw))
        except ValueError:
            continue
        urls = media_urls_from_extra(ex)
        _, v_url = pick_image_and_video_links(
            urls,
            extra=ex,
            operation=ev.operation or "",
            provider=ev.provider or "",
        )
        if not v_url or not ev.created_at:
            continue
        out.setdefault(brief_uuid, []).append((ev.created_at, v_url))
    for brief_id in out:
        out[brief_id].sort(key=lambda x: x[0])
    return out


async def _usage_media_maps_for_variants(
    variant_ids: set[UUID],
    *,
    tenant_id: UUID | None,
    platform: bool,
    since: datetime,
    until: datetime,
) -> tuple[dict[UUID, str], dict[UUID, str]]:
    """Back-fill image/video URLs from usage_events when pipeline JSON is incomplete."""
    if not variant_ids:
        return {}, {}
    from app.models.usage_event import UsageEvent

    image_by_variant: dict[UUID, str] = {}
    video_by_variant: dict[UUID, str] = {}
    async with AsyncSessionLocal() as db:
        q = select(UsageEvent).where(UsageEvent.created_at >= since).where(UsageEvent.created_at <= until)
        if not platform and tenant_id:
            q = q.where(UsageEvent.tenant_id == tenant_id)
        q = q.where(UsageEvent.success.is_(True))
        events = list((await db.execute(q)).scalars().all())
    target = {str(v) for v in variant_ids}
    for ev in events:
        ex = ev.extra or {}
        vid_raw = ex.get("variant_id")
        if not vid_raw or str(vid_raw) not in target:
            continue
        try:
            vid_uuid = UUID(str(vid_raw))
        except ValueError:
            continue
        urls = media_urls_from_extra(ex)
        img, v_url = pick_image_and_video_links(
            urls,
            extra=ex,
            operation=ev.operation or "",
            provider=ev.provider or "",
        )
        if img and vid_uuid not in image_by_variant:
            image_by_variant[vid_uuid] = img
        if v_url and vid_uuid not in video_by_variant:
            video_by_variant[vid_uuid] = v_url
    return image_by_variant, video_by_variant


async def _asset_urls_by_variant(variant_ids: set[UUID]) -> dict[UUID, list[str]]:
    if not variant_ids:
        return {}
    out: dict[UUID, list[str]] = {}
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Asset.variant_id, Asset.file_url)
            .where(Asset.variant_id.in_(variant_ids), Asset.file_url.is_not(None))
            .order_by(Asset.created_at.desc())
        )
        for variant_id, file_url in rows.all():
            if not variant_id or not file_url:
                continue
            abs_u = absolute_media_url(str(file_url))
            if not abs_u or not is_hosted_creative_file_url(abs_u):
                continue
            slot = out.setdefault(variant_id, [])
            if abs_u not in slot:
                slot.append(abs_u)
    return out


def _creative_type_label(fmt: str, image_link: str, video_link: str) -> str:
    if video_link and image_link:
        return "Image + video"
    if video_link or fmt in {"reel", "video"}:
        return "Video"
    if image_link or fmt in {"static", "carousel"}:
        return "Image"
    return ""


async def _load_creatives_by_brand_rows(
    *,
    tenant_id: UUID | None,
    platform: bool,
    since: datetime,
    until: datetime,
    user_id: UUID | None = None,
) -> list[list[Any]]:
    """Finished variants — authoritative list for client/brand managers."""
    from sqlalchemy.orm import aliased

    Creator = aliased(User)
    known_brands = await _load_known_brand_names(tenant_id=tenant_id, platform=platform)
    variant_user_map, brief_user_map, _ = await _usage_contributor_maps(
        tenant_id=tenant_id,
        platform=platform,
        since=since,
        until=until,
    )
    q = (
        select(Variant, Brand.name, Creator.email, Creator.full_name, Brief.title, Brief.product_name)
        .join(Brand, Variant.brand_id == Brand.id)
        .join(Brief, Variant.brief_id == Brief.id)
        .outerjoin(Creator, Brief.created_by == Creator.id)
        .where(Variant.created_at >= since)
        .where(Variant.created_at <= until)
        .where(Variant.status.in_(["READY", "APPROVED", "EXPORTED"]))
    )
    if not platform and tenant_id:
        q = q.where(Variant.tenant_id == tenant_id)
    brief_ids_for_user: set[UUID] = set()
    if user_id is not None:
        usage_scope = await fetch_usage_events(
            tenant_id=tenant_id,
            platform=platform,
            since=since,
            until=until,
            user_id=user_id,
            limit=MAX_EXPORT_ROWS + 1,
        )
        for ev in usage_scope:
            bid = _uuid_or_none((ev.extra or {}).get("brief_id"))
            if bid:
                brief_ids_for_user.add(bid)
        from sqlalchemy import or_

        clauses = [Creator.id == user_id, Brief.created_by == user_id]
        if brief_ids_for_user:
            clauses.append(Variant.brief_id.in_(brief_ids_for_user))
        q = q.where(or_(*clauses))
    q = q.order_by(Brand.name.asc(), Variant.created_at.desc())

    rows_out: list[list[Any]] = []
    async with AsyncSessionLocal() as db:
        result = await db.execute(q)
        batch = result.all()
    variant_ids = {v.id for v, *_ in batch}
    assets_map = await _asset_urls_by_variant(variant_ids)
    usage_img_map, usage_vid_map = await _usage_media_maps_for_variants(
        variant_ids,
        tenant_id=tenant_id,
        platform=platform,
        since=since,
        until=until,
    )
    brief_video_events = await _brief_usage_video_events(
        tenant_id=tenant_id,
        platform=platform,
        since=since,
        until=until,
    )
    asset_creator_email = await _asset_creator_email_by_variant(variant_ids)
    for variant, brand_name, email, full_name, brief_title, product_name in batch:
        img, vid = _pipeline_media_from_variant(
            variant.generation_params,
            asset_urls=assets_map.get(variant.id),
            usage_image=usage_img_map.get(variant.id, ""),
            usage_video=usage_vid_map.get(variant.id, ""),
        )
        if not vid:
            vid = _brief_usage_video_fallback(variant, brief_video_events)
        has_img, has_vid = _variant_delivery_flags(variant, img, vid)
        if not has_img and not has_vid:
            continue
        email = _sanitize_contributor_email(email or "")
        if not email:
            email = _sanitize_contributor_email(asset_creator_email.get(variant.id) or "")
        if not email:
            extra_emails = variant_user_map.get(variant.id) or brief_user_map.get(variant.brief_id) or set()
            human = sorted(_sanitize_contributor_email(e) or "" for e in extra_emails)
            human = [e for e in human if e]
            if human:
                email = human[0]
        ctype = _creative_type_label(variant.format or "", img, vid)
        if not ctype:
            if has_img and has_vid:
                ctype = "Image + video"
            elif has_vid:
                ctype = "Video"
            elif has_img:
                ctype = "Image"
        created = (
            variant.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if variant.created_at
            else ""
        )
        hook = (variant.hook or "")[:120]
        params = variant.generation_params if isinstance(variant.generation_params, dict) else {}
        hook_context = " ".join(
            p
            for p in (
                hook,
                brief_title or "",
                product_name or "",
                _brand_hints_from_params(params),
            )
            if p
        ).strip()
        display_brand, _ = _manager_brand_from_context(
            brand_name=brand_name or "",
            hook=hook_context,
            brief_title=brief_title or "",
            product_name=product_name or "",
            known_brands=known_brands,
        )
        rows_out.append(
            [
                created,
                email or "",
                full_name or "",
                display_brand,
                variant.format or "",
                ctype,
                hook,
                img,
                vid,
                variant_library_url(str(variant.id)),
                str(variant.brief_id),
                str(variant.id),
                brand_name or "",  # DB brand label (internal rollup / unassigned sheet)
                (brief_title or "")[:120],
                (product_name or "")[:120],
            ]
        )
    return rows_out


def build_usage_workbook(
    detail_rows: list[list[Any]],
    *,
    creatives_by_brand: list[list[Any]] | None = None,
) -> bytes:
    wb = Workbook()
    readme = wb.active
    readme.title = "Read me"
    for row in _readme_sheet_rows():
        readme.append(row)
    readme.column_dimensions["A"].width = 36
    readme.column_dimensions["B"].width = 72

    ws = wb.create_sheet(title="Usage detail", index=1)
    _write_sheet_headers(ws, DETAIL_HEADERS)
    for row in detail_rows:
        ws.append(row)
    link_cols = [DETAIL_HEADERS.index(h) + 1 for h in _COL_HYPERLINK_HEADERS]
    _add_hyperlinks(ws, url_col_indices=link_cols)
    _autosize_columns(ws)

    manager_rows = creatives_by_brand or []
    mgr = wb.create_sheet(title="Creatives by brand (manager)", index=2)
    _write_sheet_headers(mgr, CREATIVES_BY_BRAND_HEADERS)
    for row in manager_rows:
        mgr.append(row[: len(CREATIVES_BY_BRAND_HEADERS)])
    mgr_link_cols = [
        CREATIVES_BY_BRAND_HEADERS.index(h) + 1
        for h in (
            "Image link (click to open)",
            "Video link (click to open)",
            "Open in Creative Studio",
        )
    ]
    _add_hyperlinks(mgr, url_col_indices=mgr_link_cols)
    _autosize_columns(mgr)

    for title, group_col in (
        ("By user", _COL_USER_EMAIL),
        ("By brand", _COL_BRAND_NAME),
        ("By model", _COL_MODEL),
    ):
        sheet = wb.create_sheet(title=title)
        for row in _summary_rows(detail_rows, group_col=group_col, label=DETAIL_HEADERS[group_col]):
            sheet.append(row)
        _autosize_columns(sheet, max_width=36)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def generate_usage_export_xlsx(
    *,
    tenant_id: UUID | None,
    platform: bool,
    days: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: UUID | None = None,
) -> tuple[bytes, str]:
    since, until, label = parse_usage_date_range(
        days=days, date_from=date_from, date_to=date_to
    )
    rows = await fetch_usage_events(
        tenant_id=tenant_id,
        platform=platform,
        since=since,
        until=until,
        user_id=user_id,
        limit=MAX_EXPORT_ROWS + 1,
    )
    if len(rows) > MAX_EXPORT_ROWS:
        raise ValueError(
            f"Too many rows ({len(rows)}). Narrow the date range (max {MAX_EXPORT_ROWS} rows per export)."
        )

    user_ids = {r.user_id for r in rows if r.user_id}
    tenant_ids = {r.tenant_id for r in rows if r.tenant_id}
    brand_ids: set[UUID] = set()
    brief_ids: set[UUID] = set()
    variant_ids: set[UUID] = set()
    for r in rows:
        ex = r.extra or {}
        bid = ex.get("brand_id")
        if bid:
            try:
                brand_ids.add(UUID(str(bid)))
            except ValueError:
                pass
        for key, bucket in (("brief_id", brief_ids), ("variant_id", variant_ids)):
            raw = ex.get(key)
            if raw:
                try:
                    bucket.add(UUID(str(raw)))
                except ValueError:
                    pass

    users: dict[UUID, User] = {}
    tenants: dict[UUID, str] = {}
    brands: dict[UUID, str] = {}
    brief_brands: dict[UUID, UUID] = {}
    variant_brands: dict[UUID, UUID] = {}
    variant_asset_urls: dict[UUID, list[str]] = {}
    job_ids: set[str] = set()
    job_tenants: dict[str, str] = {}
    stored_file_paths: set[str] = set()
    for r in rows:
        ex = r.extra or {}
        jid = str(ex.get("job_id") or "").strip()
        if jid:
            job_ids.add(jid)
            if r.tenant_id:
                job_tenants[jid] = str(r.tenant_id)
        for path in _stored_paths_from_extra(ex, job_urls={}):
            stored_file_paths.add(path)

    job_metadata = _load_creative_studio_job_metadata(job_ids, job_tenants=job_tenants)
    job_media_urls = _job_urls(job_metadata)
    for meta in job_metadata.values():
        uid = _uuid_or_none(meta.get("user_id"))
        bid = _uuid_or_none(meta.get("brand_id"))
        brief_id = _uuid_or_none(meta.get("brief_id"))
        if uid:
            user_ids.add(uid)
        if bid:
            brand_ids.add(bid)
        if brief_id:
            brief_ids.add(brief_id)
    for raw in job_media_urls.values():
        norm = normalize_stored_file_url(raw)
        if norm:
            stored_file_paths.add(norm)

    file_url_to_variant: dict[str, UUID] = {}
    file_url_to_brand: dict[str, UUID] = {}
    file_url_to_user: dict[str, UUID] = {}
    pipeline_file_to_variant: dict[str, UUID] = {}
    variant_pipeline_media: dict[UUID, dict[str, str]] = {}

    async with AsyncSessionLocal() as db:
        if tenant_ids:
            trows = await db.execute(select(Tenant.id, Tenant.name).where(Tenant.id.in_(tenant_ids)))
            tenants = {row.id: row.name for row in trows.all()}
        if stored_file_paths:
            path_list = list(stored_file_paths)
            arows = await db.execute(
                select(Asset.file_url, Asset.variant_id, Asset.brand_id, Asset.created_by)
                .where(Asset.file_url.in_(path_list))
            )
            for file_url, variant_id, asset_brand_id, created_by in arows.all():
                if not file_url:
                    continue
                normalized = normalize_stored_file_url(str(file_url)) or str(file_url)
                if variant_id:
                    file_url_to_variant[normalized] = variant_id
                    variant_ids.add(variant_id)
                if asset_brand_id:
                    file_url_to_brand[normalized] = asset_brand_id
                    brand_ids.add(asset_brand_id)
                if created_by:
                    file_url_to_user[normalized] = created_by
                    user_ids.add(created_by)
        if tenant_ids:
            vpipe = await db.execute(
                select(Variant.id, Variant.brand_id, Variant.generation_params).where(
                    Variant.tenant_id.in_(tenant_ids)
                )
            )
            for vid, variant_brand_id, params in vpipe.all():
                if not isinstance(params, dict):
                    continue
                pipe = params.get("pipeline")
                if not isinstance(pipe, dict):
                    continue
                for block_key in ("image", "video"):
                    block = pipe.get(block_key)
                    if not isinstance(block, dict):
                        continue
                    norm = normalize_stored_file_url(str(block.get("url") or ""))
                    if norm:
                        pipeline_file_to_variant[norm] = vid
                        if norm in stored_file_paths:
                            variant_ids.add(vid)
                            if variant_brand_id:
                                variant_brands[vid] = variant_brand_id
                                brand_ids.add(variant_brand_id)
                img_u = absolute_media_url(str((pipe.get("image") or {}).get("url") or ""))
                vid_u = absolute_media_url(str((pipe.get("video") or {}).get("url") or ""))
                if img_u or vid_u:
                    variant_pipeline_media[vid] = {
                        "image": img_u,
                        "video": vid_u,
                    }
        if brief_ids:
            brows = await db.execute(select(Brief.id, Brief.brand_id).where(Brief.id.in_(brief_ids)))
            for row in brows.all():
                brief_brands[row.id] = row.brand_id
                brand_ids.add(row.brand_id)
        if variant_ids:
            vrows = await db.execute(select(Variant.id, Variant.brand_id).where(Variant.id.in_(variant_ids)))
            for row in vrows.all():
                variant_brands[row.id] = row.brand_id
                brand_ids.add(row.brand_id)
            arows = await db.execute(
                select(Asset.variant_id, Asset.file_url)
                .where(Asset.variant_id.in_(variant_ids), Asset.file_url.is_not(None))
                .order_by(Asset.created_at.desc())
            )
            for variant_id, file_url in arows.all():
                if not variant_id or not file_url:
                    continue
                slot = variant_asset_urls.setdefault(variant_id, [])
                abs_u = absolute_media_url(str(file_url))
                if abs_u and abs_u not in slot:
                    slot.append(abs_u)
        if user_ids:
            urows = await db.execute(select(User).where(User.id.in_(user_ids)))
            users = {u.id: u for u in urows.scalars().all()}
        if brand_ids:
            brows = await db.execute(select(Brand.id, Brand.name).where(Brand.id.in_(brand_ids)))
            brands = {row.id: row.name for row in brows.all()}

    detail = [
        _detail_row(
            r,
            users=users,
            tenants=tenants,
            brands=brands,
            brief_brands=brief_brands,
            variant_brands=variant_brands,
            variant_asset_urls=variant_asset_urls,
            job_metadata=job_metadata,
            file_url_to_variant=file_url_to_variant,
            file_url_to_brand=file_url_to_brand,
            file_url_to_user=file_url_to_user,
            pipeline_file_to_variant=pipeline_file_to_variant,
            variant_pipeline_media=variant_pipeline_media,
        )
        for r in reversed(rows)
    ]
    creatives = await _load_creatives_by_brand_rows(
        tenant_id=tenant_id,
        platform=platform,
        since=since,
        until=until,
        user_id=user_id,
    )
    content = build_usage_workbook(detail, creatives_by_brand=creatives)
    filename = f"usage-report-{label}.xlsx"
    return content, filename


def _summary_user_display(name: str, email: str) -> str:
    label = (name or "").strip()
    if label:
        return label
    if email and email != "Unknown user" and "@" in email:
        local = email.split("@", 1)[0].replace(".", " ").replace("_", " ")
        return local.title()
    if email and email != "Unknown user":
        return email
    return "Unknown"


USER_MANAGER_SUMMARY_HEADERS = [
    "User",
    "Images delivered",
    "Videos delivered",
    "Total creatives",
    "Brands / clients worked",
    "Est. spend (USD)",
    "API calls",
]

BRAND_MANAGER_SUMMARY_HEADERS = [
    "Brand / client",
    "Images delivered",
    "Videos delivered",
    "Total creatives",
    "Contributors",
    "Sample hooks / purpose",
    "Est. spend — media only (USD)",
]

NO_BRAND_BY_PERSON_HEADERS = [
    "User",
    "Images",
    "Videos",
    "Total creatives",
    "Sample brief titles",
    "Sample hooks / purpose",
    "Example links (Creative Studio)",
]

API_ONLY_NO_BRAND_HEADERS = [
    "User",
    "API image calls",
    "API video calls",
    "Note",
]

UNASSIGNED_DETAIL_HEADERS = [
    "User",
    "Brief title",
    "Product (brief)",
    "Hook / purpose",
    "Format",
    "Type",
    "Open in Creative Studio",
    "Brief ID",
]


def _summary_readme_rows(period_label: str) -> list[list[str]]:
    return [
        ["Usage summary — for reporting managers"],
        [""],
        ["Period", period_label],
        ["How to use", "Deliverable counts = finished work in Creative library (READY variants only)."],
        [
            "Videos delivered",
            "Library READY clips OR successful Seedance/Omni (task billed / output URL) — attributed via job or brief owner.",
        ],
        ["By user", "People only — Seedance service login rolls into whoever started the job."],
        ["Date range", "Same rules in the report period (default last 30 days)."],
        ["vs Creative library UI", "Library header counts all dates (up to 300) for the workspace — not one person."],
        [
            "Spend on By brand",
            "Sum of logged image/video API costs per client (brief/variant/job brand) — not LLM, not pooled guesses.",
        ],
        [
            "Seedance on By brand",
            "Same estimate as usage dashboard (stored cost_usd, else token mid or duration for 2.5).",
        ],
        ["Spend on By user / Overview", "All API usage including LLM, scrapes, and retries."],
        [""],
        ["Detail links", "Use «Download Excel (full report)» for clickable image/video URLs per creative."],
    ]


def build_summary_workbook(
    *,
    period_label: str,
    overview: list[list[Any]],
    by_user: list[list[Any]],
    by_brand: list[list[Any]],
    unassigned_by_hook: list[list[Any]] | None = None,
    no_brand_by_person: list[list[Any]] | None = None,
    api_only_no_brand: list[list[Any]] | None = None,
) -> bytes:
    wb = Workbook()
    readme = wb.active
    readme.title = "Read me"
    for row in _summary_readme_rows(period_label):
        readme.append(row)
    readme.column_dimensions["A"].width = 28
    readme.column_dimensions["B"].width = 72

    ov = wb.create_sheet("Overview", 1)
    ov.append(["Metric", "Value"])
    ov.cell(row=1, column=1).font = Font(bold=True)
    ov.cell(row=1, column=2).font = Font(bold=True)
    for row in overview:
        ov.append(row)
    _autosize_columns(ov, max_width=48)

    us = wb.create_sheet("By user", 2)
    _write_sheet_headers(us, USER_MANAGER_SUMMARY_HEADERS)
    for row in by_user:
        us.append(row)
    _autosize_columns(us)

    br = wb.create_sheet("By brand", 3)
    _write_sheet_headers(br, BRAND_MANAGER_SUMMARY_HEADERS)
    for row in by_brand:
        br.append(row)
    _autosize_columns(br)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def _build_manager_summary_tables(
    *,
    tenant_id: UUID | None,
    platform: bool,
    since: datetime,
    until: datetime,
    period_label: str,
    user_id: UUID | None = None,
) -> tuple[
    list[list[Any]],
    list[list[Any]],
    list[list[Any]],
    list[list[Any]],
    list[list[Any]],
    list[list[Any]],
]:
    from collections import defaultdict

    known_brands = await _load_known_brand_names(tenant_id=tenant_id, platform=platform)
    creatives = await _load_creatives_by_brand_rows(
        tenant_id=tenant_id,
        platform=platform,
        since=since,
        until=until,
        user_id=user_id,
    )
    usage_rows = await fetch_usage_events(
        tenant_id=tenant_id,
        platform=platform,
        since=since,
        until=until,
        user_id=user_id,
        limit=MAX_EXPORT_ROWS + 1,
    )

    user_ids = {r.user_id for r in usage_rows if r.user_id}
    brand_ids: set[UUID] = set()
    brief_ids: set[UUID] = set()
    job_ids: set[str] = set()
    job_tenants: dict[str, str] = {}
    for r in usage_rows:
        ex = r.extra or {}
        bid = _uuid_or_none(ex.get("brand_id"))
        if bid:
            brand_ids.add(bid)
        brief_id = _uuid_or_none(ex.get("brief_id"))
        if brief_id:
            brief_ids.add(brief_id)
        jid = str(ex.get("job_id") or "").strip()
        if jid:
            job_ids.add(jid)
            if r.tenant_id:
                job_tenants[jid] = str(r.tenant_id)
    job_metadata = _load_creative_studio_job_metadata(job_ids, job_tenants=job_tenants)
    seedance_task_tenants: dict[str, str | None] = {}
    for r in usage_rows:
        if not is_byteplus_seedance_row(r):
            continue
        tid = str((r.extra or {}).get("task_id") or "").strip()
        if tid and tid not in seedance_task_tenants:
            seedance_task_tenants[tid] = str(r.tenant_id) if r.tenant_id else None
    task_job_metadata = _load_task_job_metadata(seedance_task_tenants)
    for meta in list(job_metadata.values()) + list(task_job_metadata.values()):
        uid = _uuid_or_none(meta.get("user_id"))
        if uid:
            user_ids.add(uid)
        bid = _uuid_or_none(meta.get("brand_id"))
        if bid:
            brand_ids.add(bid)
        brief_id = _uuid_or_none(meta.get("brief_id"))
        if brief_id:
            brief_ids.add(brief_id)
    for r in usage_rows:
        brief_id = _uuid_or_none((r.extra or {}).get("brief_id"))
        if brief_id:
            brief_ids.add(brief_id)
    variant_ids_in_creatives: set[UUID] = set()
    variant_ids_for_brands: set[UUID] = set()
    for row in creatives:
        try:
            vid = UUID(str(row[11]))
            variant_ids_in_creatives.add(vid)
            variant_ids_for_brands.add(vid)
        except (ValueError, TypeError, IndexError):
            pass
    for r in usage_rows:
        vid = _uuid_or_none((r.extra or {}).get("variant_id"))
        if vid:
            variant_ids_for_brands.add(vid)

    brief_owners: dict[UUID, UUID] = {}
    async with AsyncSessionLocal() as db:
        brands: dict[UUID, str] = {}
        brief_brands: dict[UUID, UUID] = {}
        if brief_ids:
            brows = await db.execute(
                select(Brief.id, Brief.brand_id, Brief.created_by).where(Brief.id.in_(brief_ids))
            )
            for brow in brows.all():
                brief_brands[brow.id] = brow.brand_id
                if brow.brand_id:
                    brand_ids.add(brow.brand_id)
                if brow.created_by:
                    brief_owners[brow.id] = brow.created_by
                    user_ids.add(brow.created_by)
        users: dict[UUID, User] = {}
        if user_ids:
            urows = await db.execute(select(User).where(User.id.in_(user_ids)))
            users = {u.id: u for u in urows.scalars().all()}
        if brand_ids:
            bnames = await db.execute(select(Brand.id, Brand.name).where(Brand.id.in_(brand_ids)))
            brands = {row.id: row.name for row in bnames.all()}
        variant_brands: dict[UUID, UUID] = {}
        if variant_ids_for_brands:
            vrows = await db.execute(
                select(Variant.id, Variant.brand_id).where(Variant.id.in_(variant_ids_for_brands))
            )
            for vrow in vrows.all():
                if vrow.brand_id:
                    variant_brands[vrow.id] = vrow.brand_id
                    brand_ids.add(vrow.brand_id)
            if brand_ids:
                bnames = await db.execute(select(Brand.id, Brand.name).where(Brand.id.in_(brand_ids)))
                brands = {row.id: row.name for row in bnames.all()}

    user_acc: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "name": "",
            "images": 0,
            "videos": 0,
            "creatives": 0,
            "brands": set(),
            "cost": 0.0,
            "calls": 0,
        }
    )
    brand_acc: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "images": 0,
            "videos": 0,
            "creatives": 0,
            "users": set(),
            "hooks": set(),
            "cost": 0.0,
        }
    )
    unassigned_rows: list[list[Any]] = []
    no_brand_person: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "images": 0,
            "videos": 0,
            "creatives": 0,
            "titles": set(),
            "hooks": set(),
            "links": set(),
        }
    )
    no_brand_totals = {"images": 0, "videos": 0, "creatives": 0}
    api_no_brand_person: dict[str, dict[str, int]] = defaultdict(lambda: {"images": 0, "videos": 0})
    api_no_brand_total = {"images": 0, "videos": 0}
    delivery_dedup_keys: set[str] = set()
    media_cost_dedup_keys: set[str] = set()

    total_images = 0
    total_videos = 0
    total_creatives = 0
    for row in creatives:
        email = _sanitize_contributor_email(str(row[1] or "").strip()) or "Unknown user"
        name = str(row[2] or "").strip()
        db_brand = str(row[12] if len(row) > 12 else "").strip()
        display_brand = str(row[3] or "").strip()
        brand = _brand_summary_rollup_key(db_brand_label=db_brand, display_brand=display_brand)
        hook = str(row[6] or "").strip()
        img_link = str(row[7] or "").strip()
        vid_link = str(row[8] or "").strip()
        ctype = str(row[5] or "").strip().lower()
        counts_img = bool(img_link) or "image" in ctype
        counts_vid = bool(vid_link) or "video" in ctype
        slot_u = user_acc[email]
        slot_u["name"] = slot_u["name"] or name
        if brand != _NO_BRAND_BUCKET:
            slot_u["brands"].add(brand)
        slot_b = brand_acc[brand]
        if email != "Unknown user" and not _is_automation_service_email(email):
            slot_b["users"].add(email)
        if hook:
            slot_b["hooks"].add(_hook_sample_key(hook))
        person = _summary_user_display(name, email)
        brief_title = str(row[13] if len(row) > 13 else "").strip()
        product_name = str(row[14] if len(row) > 14 else "").strip()
        if brand == _NO_BRAND_BUCKET and (counts_img or counts_vid):
            no_brand_totals["creatives"] += 1
            if counts_img:
                no_brand_totals["images"] += 1
            if counts_vid:
                no_brand_totals["videos"] += 1
            ps = no_brand_person[person]
            ps["creatives"] += 1
            if counts_img:
                ps["images"] += 1
            if counts_vid:
                ps["videos"] += 1
            if brief_title:
                ps["titles"].add(brief_title[:80])
            if hook:
                ps["hooks"].add(_hook_sample_key(hook))
            link = str(row[9] or "").strip()
            if link and len(ps["links"]) < 5:
                ps["links"].add(link)
            unassigned_rows.append(
                [
                    person,
                    brief_title,
                    product_name,
                    hook,
                    str(row[4] or ""),
                    str(row[5] or ""),
                    link,
                    str(row[10] or ""),
                ]
            )
        if counts_img or counts_vid:
            slot_u["creatives"] += 1
            slot_b["creatives"] += 1
            total_creatives += 1
        if counts_img:
            slot_u["images"] += 1
            slot_b["images"] += 1
            total_images += 1
        if counts_vid:
            slot_u["videos"] += 1
            slot_b["videos"] += 1
            total_videos += 1
        try:
            variant_id = UUID(str(row[11]))
        except (ValueError, TypeError, IndexError):
            variant_id = None
        if variant_id:
            delivery_dedup_keys.add(f"variant:{variant_id}")

    for ev in usage_rows:
        event_job_meta = _resolve_event_job_meta(
            ev,
            job_metadata=job_metadata,
            task_job_metadata=task_job_metadata,
        )
        actor_email, actor_name = _resolve_usage_actor(
            ev,
            users=users,
            job_metadata=job_metadata,
            task_job_metadata=task_job_metadata,
            brief_owners=brief_owners,
        )
        email = actor_email
        if email and actor_name:
            user_acc[email]["name"] = user_acc[email]["name"] or actor_name
        cost = effective_cost_usd(ev)
        media_cost = _manager_media_cost_usd(ev, job_meta=event_job_meta)
        cost_email = email if email and not _is_automation_service_email(email) else "Unknown user"
        user_acc[cost_email]["cost"] += cost
        user_acc[cost_email]["calls"] += 1
        ex = ev.extra or {}
        job_meta = event_job_meta
        brand_key = _resolve_usage_brand_key(
            ev,
            job_meta=job_meta,
            brands=brands,
            brief_brands=brief_brands,
            variant_brands=variant_brands,
            known_brands=known_brands,
        )
        hook_hint = str(
            ex.get("hook") or ex.get("prompt") or ex.get("title") or (job_meta or {}).get("brand_name") or ""
        )[:120]
        if media_cost > 0:
            cost_key = _usage_media_cost_dedup_key(ev)
            if cost_key in media_cost_dedup_keys:
                media_cost = 0.0
            else:
                media_cost_dedup_keys.add(cost_key)
                brand_acc[brand_key]["cost"] += media_cost

        kind = _usage_delivery_kind(ev)
        if not kind or not _usage_has_successful_media_output(ev, job_meta=job_meta):
            continue
        if not email or _is_automation_service_email(email):
            continue
        vid = _uuid_or_none(ex.get("variant_id"))
        if vid and vid in variant_ids_in_creatives:
            continue
        if vid:
            vkey = f"variant:{vid}"
            if vkey in delivery_dedup_keys:
                continue
            delivery_dedup_keys.add(vkey)
        dedup = _usage_delivery_dedup_key(ev)
        if dedup in delivery_dedup_keys:
            continue
        delivery_dedup_keys.add(dedup)
        if brand_key != _NO_BRAND_BUCKET:
            user_acc[email]["brands"].add(brand_key)
        if email and email != "Unknown user" and not _is_automation_service_email(email):
            brand_acc[brand_key]["users"].add(email)
        if hook_hint:
            brand_acc[brand_key]["hooks"].add(_hook_sample_key(hook_hint))
        slot_u = user_acc[email]
        slot_b = brand_acc[brand_key]
        slot_u["creatives"] += 1
        slot_b["creatives"] += 1
        total_creatives += 1
        if kind == "image":
            slot_u["images"] += 1
            slot_b["images"] += 1
            total_images += 1
        else:
            slot_u["videos"] += 1
            slot_b["videos"] += 1
            total_videos += 1
        if brand_key == _NO_BRAND_BUCKET:
            person = _summary_user_display(user_acc[email]["name"], email)
            if kind == "image":
                api_no_brand_person[person]["images"] += 1
                api_no_brand_total["images"] += 1
            else:
                api_no_brand_person[person]["videos"] += 1
                api_no_brand_total["videos"] += 1

    total_cost = round(sum(effective_cost_usd(r) for r in usage_rows), 4)
    overview = [
        ["Report period", period_label],
        ["From (UTC)", since.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")],
        ["To (UTC)", until.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")],
        ["Total images delivered", total_images],
        ["Total videos delivered", total_videos],
        ["Total finished creatives", total_creatives],
        ["Active users (with API usage)", len(user_acc)],
        ["Est. total spend (USD)", total_cost],
        ["Total API calls logged", len(usage_rows)],
        ["Library creatives without client (no brand)", no_brand_totals["creatives"]],
        [
            "API image/video calls without library row (no brand)",
            api_no_brand_total["images"] + api_no_brand_total["videos"],
        ],
    ]
    by_user_rows: list[list[Any]] = []
    for email, slot in sorted(user_acc.items(), key=lambda x: (-x[1]["cost"], x[0])):
        if _is_automation_service_email(email):
            continue
        brands_list = ", ".join(sorted(b for b in slot["brands"] if b))
        by_user_rows.append(
            [
                _summary_user_display(slot["name"], email),
                slot["images"],
                slot["videos"],
                slot["creatives"],
                brands_list,
                round(slot["cost"], 4),
                slot["calls"],
            ]
        )

    email_to_person = {
        email: _summary_user_display(slot["name"], email) for email, slot in user_acc.items()
    }

    # Keep (no brand) deliverable totals aligned with «No brand by person» / detail sheets.
    if _NO_BRAND_BUCKET in brand_acc or no_brand_person:
        nb_slot = brand_acc[_NO_BRAND_BUCKET]
        nb_slot["images"] = sum(p["images"] for p in no_brand_person.values())
        nb_slot["videos"] = sum(p["videos"] for p in no_brand_person.values())
        nb_slot["creatives"] = sum(p["creatives"] for p in no_brand_person.values())
        nb_hooks: set[str] = set()
        for p in no_brand_person.values():
            nb_hooks |= p["hooks"]
        if nb_hooks:
            nb_slot["hooks"] = nb_hooks

    by_brand_rows: list[list[Any]] = []
    for brand, slot in sorted(brand_acc.items(), key=lambda x: (-(x[1]["images"] + x[1]["videos"]), x[0])):
        if brand == _NO_BRAND_BUCKET and slot["images"] + slot["videos"] == 0 and slot["cost"] <= 0:
            continue
        hook_samples = sorted(slot["hooks"])[:_MAX_HOOK_SAMPLES]
        if brand == _NO_BRAND_BUCKET:
            people = sorted(
                p
                for p in no_brand_person.keys()
                if p and "seedance" not in p.lower() and "creativestudio.tools" not in p.lower()
            )
        else:
            people = sorted(
                {
                    email_to_person.get(u, u)
                    for u in slot["users"]
                    if u and not _is_automation_service_email(u)
                }
            )
        by_brand_rows.append(
            [
                brand,
                slot["images"],
                slot["videos"],
                slot["creatives"],
                ", ".join(people),
                " | ".join(hook_samples),
                round(slot["cost"], 4),
            ]
        )

    no_brand_by_person_rows: list[list[Any]] = []
    for person, ps in sorted(
        no_brand_person.items(),
        key=lambda x: (-(x[1]["images"] + x[1]["videos"]), x[0]),
    ):
        no_brand_by_person_rows.append(
            [
                person,
                ps["images"],
                ps["videos"],
                ps["creatives"],
                " | ".join(sorted(ps["titles"])[:5]),
                " | ".join(sorted(ps["hooks"])[:5]),
                " | ".join(sorted(ps["links"])[:5]),
            ]
        )

    api_only_rows: list[list[Any]] = []
    for person, counts in sorted(
        api_no_brand_person.items(),
        key=lambda x: (-(x[1]["images"] + x[1]["videos"]), x[0]),
    ):
        if counts["images"] + counts["videos"] == 0:
            continue
        api_only_rows.append(
            [
                person,
                counts["images"],
                counts["videos"],
                "API generation logged — not a READY variant in library (see full Excel for raw events).",
            ]
        )

    unassigned_rows.sort(key=lambda r: ((r[0] or "").lower(), (r[1] or "").lower()))
    return (
        overview,
        by_user_rows,
        by_brand_rows,
        unassigned_rows,
        no_brand_by_person_rows,
        api_only_rows,
    )


async def generate_usage_summary_xlsx(
    *,
    tenant_id: UUID | None,
    platform: bool,
    days: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: UUID | None = None,
) -> tuple[bytes, str]:
    since, until, label = parse_usage_date_range(
        days=days, date_from=date_from, date_to=date_to
    )
    overview, by_user, by_brand, unassigned, no_brand_people, api_only = await _build_manager_summary_tables(
        tenant_id=tenant_id,
        platform=platform,
        since=since,
        until=until,
        period_label=label.replace("_", " "),
        user_id=user_id,
    )
    content = build_summary_workbook(
        period_label=label.replace("_", " "),
        overview=overview,
        by_user=by_user,
        by_brand=by_brand,
        unassigned_by_hook=unassigned,
        no_brand_by_person=no_brand_people,
        api_only_no_brand=api_only,
    )
    filename = f"usage-summary-{label}.xlsx"
    return content, filename
