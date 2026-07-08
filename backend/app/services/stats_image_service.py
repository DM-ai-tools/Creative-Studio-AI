"""Extract ROAS / ROI / conversion stats from performance dashboard screenshots."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

from app.core.config import settings
from app.schemas.avatar_script import PerformanceStatsContext

logger = logging.getLogger(__name__)

# Gemini on OpenRouter — ordered fallbacks for dashboard OCR / vision
GEMINI_VISION_MODELS = (
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    "google/gemini-3-flash-preview",
)

STATS_EXTRACTION_PROMPT = """You are an OCR + data extraction expert for marketing dashboard screenshots (Google Ads, Meta, ClickTrends ROAS/ROI reports).

Read EVERY number, label, and callout box in the image carefully.

Return ONLY valid JSON (no markdown fences) with this FLAT structure — use empty string or [] if not visible:
{
  "industry": "e.g. E-commerce Industry, Fitness Industry, Retail Industry",
  "campaign_type": "e.g. Lead Gen Campaign",
  "headline_stat": "most prominent callout e.g. 17X ROAS, From $0 to $105M, 488% ROAS",
  "roas": "e.g. 488.87% or 17X",
  "roi": "",
  "conversions": "",
  "clicks": "",
  "purchases_sales": "",
  "revenue": "",
  "conversion_value": "e.g. 27.9M",
  "cost": "",
  "cost_per_conversion": "",
  "conv_value_per_cost": "e.g. 4.89",
  "lead_forms": "e.g. 1.26M",
  "timeline": "e.g. Mar 2025 to Apr 2026",
  "growth_story": "one sentence describing the visible chart trend",
  "metrics": [{"label": "Actual ROAS", "value": "488.87%"}],
  "script_proof_lines": ["short spoken proof line with exact numbers from image"]
}

Rules:
- OCR all visible metric cards (top row numbers, side callout boxes, chart axis labels)
- Extract EXACT numbers as displayed — never invent stats not shown
- script_proof_lines: 2-4 punchy spoken-friendly proof lines using real figures — Australian English phrasing. Write every figure as NUMERALS with its unit/magnitude word so it reads clearly in captions (e.g. "488% ROAS", "$18.9 million in spend", "$105 million", "over 1.2 million leads"). Never spell figures out as words (not "four hundred and eighty-eight per cent")
- Preserve units: %, X, K, M, $ as displayed
- If a callout says "Lead Gen Campaign 488% ROAS", set campaign_type and headline_stat accordingly"""


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _normalize_stats_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested Gemini responses and alias common dashboard field names."""
    flat: dict[str, Any] = dict(data)

    roas_obj = flat.pop("roas", None)
    if isinstance(roas_obj, dict):
        actual = _as_str(roas_obj.get("actual_roas") or roas_obj.get("actual"))
        campaign = _as_str(
            roas_obj.get("lead_gen_campaign_roas")
            or roas_obj.get("campaign_roas")
            or roas_obj.get("headline")
        )
        flat.setdefault("roas", actual or campaign)
        flat.setdefault("headline_stat", campaign or actual)
    elif roas_obj is not None:
        flat.setdefault("roas", _as_str(roas_obj))

    conv_obj = flat.pop("conversions", None)
    if isinstance(conv_obj, dict):
        flat.setdefault(
            "conv_value_per_cost",
            _as_str(conv_obj.get("conv_value_cost") or conv_obj.get("conv_value_per_cost")),
        )
        flat.setdefault("conversion_value", _as_str(conv_obj.get("conv_value")))
        flat.setdefault(
            "lead_forms",
            _as_str(conv_obj.get("submit_lead_forms") or conv_obj.get("lead_forms")),
        )
        flat.setdefault("conversions", _as_str(conv_obj.get("conversions") or conv_obj.get("total")))
    elif conv_obj is not None:
        flat.setdefault("conversions", _as_str(conv_obj))

    # Common alternate keys from OCR
    aliases = {
        "actual_roas": "roas",
        "submit_lead_forms": "lead_forms",
        "conv_value_cost": "conv_value_per_cost",
        "purchases": "purchases_sales",
        "sales": "purchases_sales",
    }
    for src, dest in aliases.items():
        if src in flat and not _as_str(flat.get(dest)):
            flat[dest] = _as_str(flat.pop(src))

    return flat


def _stats_has_content(ctx: PerformanceStatsContext) -> bool:
    if ctx.headline_stat or ctx.roas or ctx.conversions or ctx.lead_forms:
        return True
    if ctx.metrics or ctx.script_proof_lines:
        return True
    return any(
        _as_str(getattr(ctx, field))
        for field in (
            "industry",
            "campaign_type",
            "roi",
            "clicks",
            "purchases_sales",
            "revenue",
            "conversion_value",
            "cost",
            "cost_per_conversion",
            "conv_value_per_cost",
        )
    )


def format_per_image_stats_for_script(
    contexts: list[PerformanceStatsContext],
) -> str:
    """One OCR block per dashboard image — pairs with [INSERT STAT IMAGE N]."""
    if not contexts:
        return ""
    parts: list[str] = []
    for i, stats in enumerate(contexts, start=1):
        block = format_performance_stats_for_script(stats).strip()
        headline = (stats.headline_stat or stats.roas or stats.industry or f"Dashboard {i}").strip()
        parts.append(
            f"STAT IMAGE {i} — cite these EXACT figures when [INSERT STAT IMAGE {i}] appears:\n"
            f"Headline: {headline}\n{block}"
        )
    return "\n\n".join(parts)


def format_performance_stats_for_script(stats: PerformanceStatsContext) -> str:
    """Plain-text block fed into script-generation prompts."""
    if stats.summary_for_script.strip():
        return stats.summary_for_script.strip()

    lines: list[str] = []
    if stats.industry:
        lines.append(f"Industry: {stats.industry}")
    if stats.campaign_type:
        lines.append(f"Campaign: {stats.campaign_type}")
    if stats.headline_stat:
        lines.append(f"Headline result: {stats.headline_stat}")
    for field, label in (
        (stats.roas, "ROAS"),
        (stats.roi, "ROI"),
        (stats.conversions, "Conversions"),
        (stats.clicks, "Clicks"),
        (stats.purchases_sales, "Purchases / Sales"),
        (stats.revenue, "Revenue"),
        (stats.conversion_value, "Conversion value"),
        (stats.cost, "Ad spend / Cost"),
        (stats.cost_per_conversion, "Cost per conversion"),
        (stats.conv_value_per_cost, "Conv. value / cost"),
        (stats.lead_forms, "Lead form submissions"),
    ):
        if field and str(field).strip():
            lines.append(f"{label}: {field}")
    if stats.timeline:
        lines.append(f"Timeline: {stats.timeline}")
    if stats.growth_story:
        lines.append(f"Growth: {stats.growth_story}")
    for m in stats.metrics:
        label = getattr(m, "label", "") or (m.get("label") if isinstance(m, dict) else "")
        value = getattr(m, "value", "") or (m.get("value") if isinstance(m, dict) else "")
        if label and value:
            lines.append(f"{label}: {value}")
    if stats.script_proof_lines:
        lines.append("Proof lines to weave into dialogue:")
        for line in stats.script_proof_lines:
            if line.strip():
                lines.append(f"  • {line.strip()}")
    return "\n".join(lines)


def merge_performance_stats(
    contexts: list[PerformanceStatsContext],
) -> PerformanceStatsContext | None:
    """Combine OCR results from multiple dashboard screenshots."""
    valid = [c for c in contexts if c is not None]
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0]

    merged = PerformanceStatsContext()
    industries: list[str] = []
    campaigns: list[str] = []
    proof_lines: list[str] = []
    metrics: list[dict[str, str]] = []
    summaries: list[str] = []

    scalar_fields = (
        "headline_stat",
        "roas",
        "roi",
        "conversions",
        "clicks",
        "purchases_sales",
        "revenue",
        "conversion_value",
        "cost",
        "cost_per_conversion",
        "conv_value_per_cost",
        "lead_forms",
        "timeline",
        "growth_story",
    )

    for i, ctx in enumerate(valid, start=1):
        label = ctx.industry or ctx.campaign_type or f"Dashboard {i}"
        if ctx.industry and ctx.industry not in industries:
            industries.append(ctx.industry)
        if ctx.campaign_type and ctx.campaign_type not in campaigns:
            campaigns.append(ctx.campaign_type)
        for line in ctx.script_proof_lines:
            if line.strip() and line.strip() not in proof_lines:
                proof_lines.append(line.strip())
        for m in ctx.metrics:
            lbl = getattr(m, "label", "") or (m.get("label") if isinstance(m, dict) else "")
            val = getattr(m, "value", "") or (m.get("value") if isinstance(m, dict) else "")
            if lbl and val:
                metrics.append({"label": f"{label}: {lbl}", "value": str(val)})
        block = format_performance_stats_for_script(ctx).strip()
        if block:
            summaries.append(f"--- {label} ---\n{block}")

        for field in scalar_fields:
            val = str(getattr(ctx, field, "") or "").strip()
            if not val:
                continue
            existing = str(getattr(merged, field, "") or "").strip()
            if not existing:
                setattr(merged, field, val)
            elif val not in existing:
                setattr(merged, field, f"{existing}; {val}")

    merged.industry = " · ".join(industries) if industries else merged.industry
    merged.campaign_type = " · ".join(campaigns) if campaigns else merged.campaign_type
    merged.script_proof_lines = proof_lines
    merged.metrics = metrics
    merged.summary_for_script = (
        "\n\n".join(summaries) if summaries else format_performance_stats_for_script(merged)
    )
    return merged


def performance_stats_to_context(data: dict[str, Any]) -> PerformanceStatsContext:
    data = _normalize_stats_payload(data)
    metrics_raw = data.get("metrics") or []
    metrics: list[dict[str, str]] = []
    if isinstance(metrics_raw, list):
        for item in metrics_raw:
            if isinstance(item, dict):
                metrics.append(
                    {
                        "label": str(item.get("label") or ""),
                        "value": str(item.get("value") or ""),
                    }
                )

    proof_raw = data.get("script_proof_lines") or []
    proof_lines = [str(x).strip() for x in proof_raw if str(x).strip()] if isinstance(proof_raw, list) else []

    ctx = PerformanceStatsContext(
        industry=str(data.get("industry") or "").strip(),
        campaign_type=str(data.get("campaign_type") or "").strip(),
        headline_stat=str(data.get("headline_stat") or "").strip(),
        roas=str(data.get("roas") or "").strip(),
        roi=str(data.get("roi") or "").strip(),
        conversions=str(data.get("conversions") or "").strip(),
        clicks=str(data.get("clicks") or "").strip(),
        purchases_sales=str(data.get("purchases_sales") or "").strip(),
        revenue=str(data.get("revenue") or "").strip(),
        conversion_value=str(data.get("conversion_value") or "").strip(),
        cost=str(data.get("cost") or "").strip(),
        cost_per_conversion=str(data.get("cost_per_conversion") or "").strip(),
        conv_value_per_cost=str(data.get("conv_value_per_cost") or "").strip(),
        lead_forms=str(data.get("lead_forms") or "").strip(),
        timeline=str(data.get("timeline") or "").strip(),
        growth_story=str(data.get("growth_story") or "").strip(),
        metrics=metrics,
        script_proof_lines=proof_lines,
    )
    ctx.summary_for_script = format_performance_stats_for_script(ctx)
    return ctx


_INSERT_STAT_MARKER = re.compile(r"\[INSERT\s+STAT\s+IMAGE\s*(\d+)\]", re.IGNORECASE)


def _coerce_stats_context(item: Any) -> PerformanceStatsContext | None:
    if item is None:
        return None
    if isinstance(item, PerformanceStatsContext):
        return item
    if isinstance(item, dict):
        return performance_stats_to_context(item)
    return None


def resolve_performance_stats_per_image_from_brief(brief: dict | None) -> list[PerformanceStatsContext]:
    """Per-dashboard OCR from brief key_benefits (saved at script/export time)."""
    if not brief:
        return []
    kb = brief.get("key_benefits")
    if not isinstance(kb, dict):
        kb = {}
    raw = kb.get("performance_stats_per_image")
    if isinstance(raw, list) and raw:
        out: list[PerformanceStatsContext] = []
        for item in raw:
            ctx = _coerce_stats_context(item)
            if ctx:
                out.append(ctx)
        if out:
            return out
    single = kb.get("performance_stats") or brief.get("performance_stats")
    ctx = _coerce_stats_context(single)
    if not ctx:
        return []
    from app.services.video_script_skeleton import resolve_stats_image_urls

    n = len(resolve_stats_image_urls(brief))
    return [ctx] if n <= 1 else [ctx] * n


def build_spoken_proof_line_for_image(
    stats: PerformanceStatsContext,
    *,
    brand_name: str = "",
) -> str:
    """One spoken proof line that cites the OCR figures for a single dashboard image."""
    if stats.script_proof_lines:
        line = stats.script_proof_lines[0].strip()
        if line:
            brand = (brand_name or "").strip()
            if brand and brand.lower() not in line.lower():
                rest = line[0].lower() + line[1:] if len(line) > 1 else line
                line = f"At {brand}, {rest}"
            return line if line.endswith((".", "!", "?")) else f"{line}."

    headline = (stats.headline_stat or stats.roas or stats.roi or "").strip()
    brand = (brand_name or "").strip()
    opener = f"At {brand}, " if brand else ""

    if stats.industry and headline:
        lead = f"{opener}for {stats.industry.lower()}, {headline}"
    elif stats.campaign_type and headline:
        lead = f"{opener}on {stats.campaign_type.lower()}, we delivered {headline}"
    elif headline:
        lead = f"{opener}we delivered {headline}"
    else:
        lead = f"{opener}here are the results"

    details: list[str] = []
    if stats.purchases_sales and stats.cost:
        details.append(
            f"{stats.purchases_sales} in purchases and sales from {stats.cost} in ad spend"
        )
    elif stats.purchases_sales:
        details.append(f"{stats.purchases_sales} in purchases and sales")
    elif stats.cost:
        details.append(f"{stats.cost} in ad spend")
    if stats.conv_value_per_cost:
        details.append(f"averaging {stats.conv_value_per_cost} times return on ad spend")
    if stats.lead_forms:
        details.append(f"{stats.lead_forms} lead form submissions")
    if stats.conversion_value:
        details.append(f"{stats.conversion_value} in conversion value")
    if stats.cost_per_conversion:
        details.append(f"{stats.cost_per_conversion} cost per conversion")
    if stats.timeline:
        details.append(f"from {stats.timeline}")

    if details:
        line = f"{lead}, with {', '.join(details[:4])}."
    else:
        line = lead if lead.endswith((".", "!", "?")) else f"{lead}."
    return line


def spoken_line_matches_stats(
    spoken: str,
    stats: PerformanceStatsContext,
    *,
    line_start_sec: float | None = None,
    script_duration: float | None = None,
) -> bool:
    """True when the spoken line cites figures from this specific dashboard."""
    from app.services.video_script_skeleton import _spoken_cites_stat

    if re.search(r"\[INSERT\s+STAT\s+IMAGE\s+\d+\]", spoken or "", re.I):
        return True

    clean = _INSERT_STAT_MARKER.sub("", spoken or "").strip()
    if not clean:
        return False

    # Hook lines often mention generic "$2 million" — never fuzzy-match OCR in the opening zone.
    if (
        line_start_sec is not None
        and script_duration is not None
        and script_duration > 30
    ):
        hook_end = min(45.0, max(10.0, float(script_duration) * 0.22))
        if float(line_start_sec) < hook_end:
            return False

    fields = (
        stats.headline_stat,
        stats.roas,
        stats.purchases_sales,
        stats.cost,
        stats.lead_forms,
        stats.conversion_value,
        stats.conv_value_per_cost,
    )
    matches = sum(1 for val in fields if val and _spoken_cites_stat(clean, str(val)))
    if matches >= 2:
        return True
    if matches == 1 and stats.headline_stat and _spoken_cites_stat(
        clean, str(stats.headline_stat)
    ):
        return True
    return False


def _format_ts(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def inject_ocr_proof_into_avatar_script(
    full_script: str,
    stats_per_image: list[PerformanceStatsContext],
    *,
    brand_name: str = "",
    duration: int = 60,
    broll_script: str = "",
) -> str:
    """
    Restructure proof zone to EXACTLY one spoken line per stat image (OCR-backed).
    Drops extra proof lines that would show the wrong dashboard on screen.
    """
    from app.services.video_script_skeleton import (
        MIN_STAT_SLIDE_SEC,
        _line_is_proof_beat,
        _timestamp_to_seconds,
        parse_broll_stat_insert_cues,
        parse_spoken_lines,
    )

    script = (full_script or "").strip()
    stats_list = [s for s in stats_per_image if s]
    n = len(stats_list)
    if not script or not n:
        return full_script

    timed = parse_spoken_lines(script, duration=duration)
    if not timed:
        return full_script

    proof_start_sec = float(duration) * 0.48
    cta_zone_start = float(duration) * 0.80

    pre: list[tuple[str, str, str]] = []
    tail: list[tuple[str, str, str]] = []
    proof_times: list[tuple[str, str]] = []

    for start, end, say in timed:
        sec = float(_timestamp_to_seconds(start))
        clean = _INSERT_STAT_MARKER.sub("", say).strip()
        is_marker = bool(_INSERT_STAT_MARKER.search(say))
        is_proof = _line_is_proof_beat(say) or is_marker
        is_cta = bool(
            re.search(
                r"\b(learn more|book\b|audit today|get my|sign up|call us|free audit)\b",
                clean,
                re.I,
            )
        )

        if sec >= cta_zone_start or (is_cta and not is_proof):
            tail.append((start, end, clean))
        elif is_proof and sec >= proof_start_sec:
            proof_times.append((start, end))
        elif sec < proof_start_sec:
            pre.append((start, end, clean))
        else:
            # Solution / bridge lines between proof and CTA (e.g. audit offer)
            tail.insert(0, (start, end, clean))

    # Prefer B-roll [INSERT STAT IMAGE N] timestamps for overlay sync
    cues = parse_broll_stat_insert_cues(broll_script, duration=duration)
    slot_times: list[tuple[str, str]] = []
    for i in range(n):
        cue = next((c for c in cues if int(c["image_index"]) == i), None)
        if cue:
            slot_times.append((_format_ts(cue["start"]), _format_ts(cue["end"])))
        elif i < len(proof_times):
            slot_times.append(proof_times[i])

    if len(slot_times) < n:
        window_start = (
            float(_timestamp_to_seconds(proof_times[0][0]))
            if proof_times
            else proof_start_sec
        )
        window_end = (
            float(_timestamp_to_seconds(proof_times[-1][1]))
            if proof_times
            else min(float(duration), cta_zone_start)
        )
        if tail:
            window_end = min(window_end, float(_timestamp_to_seconds(tail[0][0])))
        span = max(MIN_STAT_SLIDE_SEC * n, window_end - window_start)
        seg = span / n
        slot_times = []
        for i in range(n):
            s = window_start + i * seg
            e = min(window_end, s + seg)
            slot_times.append((_format_ts(s), _format_ts(e)))

    proof_lines: list[str] = []
    for i in range(n):
        s, e = slot_times[i]
        proof = build_spoken_proof_line_for_image(stats_list[i], brand_name=brand_name)
        proof_lines.append(f"[{s} - {e}] [INSERT STAT IMAGE {i + 1}] {proof}")

    out = [f"[{s} - {e}] {t}" for s, e, t in pre]
    out.extend(proof_lines)
    out.extend(f"[{s} - {e}] {t}" for s, e, t in tail)
    return "\n".join(out)


def _script_already_cites_all_images(
    script: str,
    per_image: list[PerformanceStatsContext],
) -> bool:
    """True when the approved voice script already SPEAKS every image's numbers.

    The [INSERT STAT IMAGE N] markers live in the B-roll column, NOT the spoken
    voice script — so we must NOT require them here. We only check that the
    approved dialogue already mentions each dashboard's figures. When it does,
    the script is left byte-for-byte identical to the approved master script
    (the render must never reorder/rewrite what the user approved). Card timing
    is handled separately from the B-roll cues + HeyGen SRT.
    """
    n = len(per_image)
    if n == 0:
        return True
    for i in range(n):
        if not spoken_line_matches_stats(script, per_image[i]):
            return False
    return True


def ensure_avatar_script_cites_ocr_stats(brief: dict, *, duration: int) -> dict:
    """Before HeyGen render: align approved voice script with per-image OCR proof lines.

    If the approved script ALREADY cites every image correctly, it is returned
    untouched so the rendered video matches the approved master script exactly.
    """
    kb = brief.get("key_benefits") if isinstance(brief.get("key_benefits"), dict) else {}
    script = str(brief.get("avatar_script") or kb.get("avatar_script") or "").strip()
    per_image = resolve_performance_stats_per_image_from_brief(brief)
    if not script or not per_image:
        return brief

    # Trust the approved master script when it is already aligned — no rewrite.
    if _script_already_cites_all_images(script, per_image):
        return brief

    brand = str(brief.get("brand_name") or brief.get("product_name") or "").strip()
    from app.services.video_script_skeleton import _heygen_scene_broll_raw

    broll = _heygen_scene_broll_raw(brief)
    fixed = inject_ocr_proof_into_avatar_script(
        script,
        per_image,
        brand_name=brand,
        duration=duration,
        broll_script=broll,
    )
    if fixed == script:
        return brief

    updated = {**brief, "avatar_script": fixed}
    if kb:
        updated["key_benefits"] = {**kb, "avatar_script": fixed}
    return updated


def _mock_stats_from_filename(filename: str) -> PerformanceStatsContext:
    name = (filename or "").lower()
    if "fitness" in name:
        return performance_stats_to_context(
            {
                "industry": "Fitness Industry",
                "headline_stat": "17X ROAS",
                "roas": "17X",
                "conversions": "3.39K",
                "purchases_sales": "2.09M",
                "cost": "$419K",
                "cost_per_conversion": "$123",
                "timeline": "Mar 2025 to Apr 2026",
                "script_proof_lines": [
                    "Fitness brands on our platform hit 17X ROAS.",
                    "Over three thousand conversions at just $123 per conversion.",
                ],
            }
        )
    if "retail" in name:
        return performance_stats_to_context(
            {
                "industry": "Retail Industry",
                "headline_stat": "4560 Conversions",
                "conversions": "4.56K",
                "clicks": "65.6K",
                "cost": "$132K",
                "cost_per_conversion": "$29.03",
                "script_proof_lines": [
                    "Retail campaigns drove over four and a half thousand conversions.",
                    "Cost per conversion came in at just twenty-nine dollars.",
                ],
            }
        )
    if "leadgen" in name or "lead" in name:
        return performance_stats_to_context(
            {
                "campaign_type": "Lead Gen Campaign",
                "headline_stat": "488% ROAS",
                "roas": "488.87%",
                "conversion_value": "27.9M",
                "lead_forms": "1.26M",
                "conv_value_per_cost": "4.89",
                "script_proof_lines": [
                    "Lead gen campaigns returned nearly five hundred percent ROAS.",
                    "Over one point two million lead form submissions.",
                ],
            }
        )
    return performance_stats_to_context(
        {
            "industry": "E-commerce Industry",
            "headline_stat": "From $0 to $2.42M",
            "purchases_sales": "2.42M",
            "cost": "$337K",
            "cost_per_conversion": "$44.94",
            "timeline": "Q2 2025 to Q2 2026",
            "script_proof_lines": [
                "E-commerce clients scaled from zero to over two million in sales.",
                "Cost per conversion under forty-five dollars.",
            ],
        }
    )


def _vision_model_candidates() -> list[str]:
    primary = (settings.OPENROUTER_MODEL_VISION or "").strip()
    models: list[str] = []
    if primary:
        models.append(primary)
    for m in GEMINI_VISION_MODELS:
        if m not in models:
            models.append(m)
    return models


def _call_gemini_vision(client: Any, *, model: str, data_url: str) -> str:
    """Gemini vision OCR — single user turn works best on OpenRouter."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": STATS_EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    },
                ],
            }
        ],
        max_tokens=1500,
        temperature=0.1,
    )
    return (response.choices[0].message.content or "").strip()


def _guess_image_mime(raw: bytes, filename: str, content_type: str | None) -> str:
    """Accept uploads even when the browser omits Content-Type."""
    if content_type and content_type.startswith("image/"):
        return content_type
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:2] == b"\xff\xd8":
        return "image/jpeg"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    name = (filename or "").lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".webp"):
        return "image/webp"
    if raw:
        return "image/png"
    raise ValueError("Upload a PNG, JPEG, or WebP image")


async def extract_stats_from_image(
    image_bytes: bytes,
    *,
    mime_type: str = "image/png",
    filename: str = "",
) -> PerformanceStatsContext:
    if not image_bytes:
        raise ValueError("Empty image file")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise ValueError("Image too large — max 10 MB")

    if not settings.OPENROUTER_API_KEY:
        logger.warning("No OPENROUTER_API_KEY — using filename-based mock stats")
        return _mock_stats_from_filename(filename)

    from app.services.ai_service import ai_service

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    media_type = mime_type if mime_type.startswith("image/") else "image/png"
    data_url = f"data:{media_type};base64,{b64}"

    client = ai_service._get_client()
    last_error: Exception | None = None

    for model in _vision_model_candidates():
        try:
            raw = _call_gemini_vision(client, model=model, data_url=data_url)
            data = _parse_json_object(raw)
            ctx = performance_stats_to_context(data)
            if not _stats_has_content(ctx):
                raise ValueError("No stats found in image response")
            logger.info("Stats OCR succeeded with %s for %s", model, filename or "upload")
            return ctx
        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning("Stats OCR JSON parse failed (%s): %s", model, exc)
        except Exception as exc:
            last_error = exc
            logger.warning("Stats OCR failed (%s): %s", model, exc)

    logger.exception("All Gemini vision models failed for stats OCR")
    if last_error:
        raise ValueError(
            f"Could not read stats from image — {last_error}"
        ) from last_error
    raise ValueError("Could not read stats from image — try a clearer screenshot")
