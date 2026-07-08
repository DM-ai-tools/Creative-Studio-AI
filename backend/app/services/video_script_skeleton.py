"""30-second production script skeleton — shared driver for HeyGen and Runway Veo."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.brand_prompt import clamp_runway_image_prompt
from app.services.cta_defaults import resolve_campaign_cta
from app.services.heygen_prompt import (
    AVATAR_EXPRESSION_SYNC_RULE,
    BROLL_FULL_FRAME_RULES,
    BROLL_NO_RANDOM_RULE,
    BROLL_STATS_POSTPROCESS_RULES,
    HEYGEN_FORBID_STATS_GRAPHICS_RULE,
    infer_avatar_expression_for_line,
    strip_insert_stat_placeholders,
)
from app.services.industries import resolve_target_industry
from app.services.australian_copy import AUSTRALIAN_ENGLISH_SCRIPT_RULES, AUSTRALIAN_HEYGEN_VOICE_RULE

logger = logging.getLogger(__name__)

SKELETON_VERSION = "8"  # v8: script-synced avatar expressions (no constant smile)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "video_script_skeleton.txt"
# ~2.2 words/sec keeps spoken lines short enough for 30s Meta reels (HeyGen often runs long otherwise)
WPS = 2.2
RUNWAY_VIDEO_PROMPT_MAX = 1000

_SPOKEN_BLOCK = re.compile(
    r"(?:Avatar Speaks|VO):\s*\n(.+?)(?=\n\n|\n\[|\nOn-Screen|\nScene |\nAVATAR|\nVISUAL|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_SPOKEN_LABEL = re.compile(
    r"(Avatar Speaks|VO):\s*\n(.+?)(?=\n\n|\n\[|\nOn-Screen|\nScene |\nAVATAR|\nVISUAL|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_TIMED_LINE = re.compile(
    r"\[(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})\]\s*(.+?)(?=\[\d{1,2}:\d{2}|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_SCENE_DIRECTION = re.compile(
    r"(Scene Direction:)\s*\n(.+?)(?=\nAvatar Attire:|\nBackground:|\nOn-Screen|\nAvatar Speaks|\nVO:|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _kb(brief: dict) -> dict:
    raw = brief.get("key_benefits")
    return raw if isinstance(raw, dict) else {}


def is_pdf_script_mode(brief: dict) -> bool:
    return _kb(brief).get("script_source") == "pdf"


def is_custom_script_mode(brief: dict) -> bool:
    return _kb(brief).get("script_source") in {"custom", "skeleton"}


def _join_labels(items: Any, fallback: str = "") -> str:
    if not items:
        return fallback
    if isinstance(items, list):
        parts: list[str] = []
        for item in items:
            if isinstance(item, dict):
                parts.append(str(item.get("label") or item.get("id") or ""))
            else:
                parts.append(str(item))
        return ", ".join(p for p in parts if p) or fallback
    return str(items)


def _notes_for_ai(brief: dict) -> str:
    kb = _kb(brief)
    for key in ("notes_for_ai", "brief_notes", "notes"):
        val = kb.get(key) or brief.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return str(brief.get("objective") or "").strip()


def _geography(brief: dict) -> str:
    kb = _kb(brief)
    audience = kb.get("audience") or brief.get("target_audience") or ""
    if isinstance(audience, dict):
        geo = audience.get("geography") or audience.get("location") or audience.get("country")
        if geo:
            return str(geo)
    text = str(audience)
    for token in ("Australia", "AU", "United States", "UK", "New Zealand"):
        if token.lower() in text.lower():
            return token if token != "AU" else "Australia"
    lang = str(brief.get("language") or kb.get("language") or "").lower()
    if "en-au" in lang or "australia" in lang:
        return "Australia"
    return "Australia"


def build_skeleton_context(
    brief: dict,
    copy: dict | None = None,
    *,
    duration: int = 30,
    format_type: str = "reel",
) -> dict[str, str]:
    copy = copy or {}
    kb = _kb(brief)
    _, industry_label = resolve_target_industry(brief)
    industry = (
        str(brief.get("target_industry_label") or "").strip()
        or industry_label
        or "local business"
    )
    brand = str(brief.get("brand_name") or brief.get("product_name") or "the brand")
    offer = str(kb.get("offer") or copy.get("offer") or "").strip()
    objective = str(brief.get("objective") or kb.get("campaign_focus") or "").strip()
    tone = str(brief.get("ad_copy_tone") or "confident and warm").strip()
    cta = str(copy.get("cta") or resolve_campaign_cta(brief) or "Learn more").strip()
    hook = str(copy.get("hook") or "").strip()
    headline = str(copy.get("headline") or "").strip()
    body = str(copy.get("body_copy") or "").strip()
    notes = _notes_for_ai(brief)
    geo = _geography(brief)
    placements = _join_labels(kb.get("placements") or brief.get("placements"), "Meta Reels")
    creative_formats = _join_labels(
        kb.get("creative_formats") or brief.get("formats") or [format_type],
        format_type,
    )
    hooks_fw = _join_labels(kb.get("hook_frameworks") or brief.get("hook_frameworks"), "")
    languages = str(brief.get("language") or kb.get("language") or "English")
    if format_type in {"reel", "stories"}:
        aspect = "9:16"
    elif format_type == "video":
        aspect = "16:9"
    else:
        aspect = "1:1"
    brief_name = str(
        brief.get("campaign_product") or brief.get("product_name") or brand
    ).strip()

    hook_onscreen = (
        f"Still wasting ad spend in {industry}?"
        if not offer
        else f"{offer.rstrip('.')}?"
    )
    hook_vo = hook or (
        f"If you run a {industry} business in {geo}, this will save you hours every week."
    )

    problem_onscreen = (
        f"Leads slip through the cracks\n"
        f"Ad spend with no return\n"
        f"Competitors winning in {industry}"
    )
    problem_vo = body or (
        f"You are not alone — most {industry} owners struggle with {objective or 'inconsistent leads'}."
        f" {hooks_fw + '. ' if hooks_fw else ''}It is exhausting."
    )

    solution_onscreen = offer or f"The smarter way to grow your {industry} business"
    solution_vo = (
        f"{brand} helps {industry} businesses in {geo} get predictable results."
        f" {notes[:200] + ' ' if notes else ''}"
        f"{headline or 'Real growth, without the guesswork.'}"
    ).strip()

    proof_onscreen = (
        f"+38% more leads | 2.1x ROAS | 30 days to results"
        if industry.lower() == "general"
        else f"More booked jobs | Lower cost per lead | {geo} businesses winning"
    )
    proof_vo = (
        f"{industry} owners across {geo} are seeing real outcomes — more leads, better ROI, less stress."
    )

    site = str(kb.get("website") or brief.get("website") or "").strip()
    cta_onscreen = f"{cta}\n{site}" if site else cta
    cta_vo = f"{cta}. {offer + ' — ' if offer else ''}Tap below before spots fill up."

    return {
        "BRIEF_NAME": brief_name,
        "BRAND": brand,
        "PLACEMENTS": placements,
        "CREATIVE_FORMATS": creative_formats,
        "DURATION": f"{duration} seconds",
        "LANGUAGES": languages,
        "TONE": tone,
        "CLIENT_INDUSTRY": industry,
        "GEOGRAPHY": geo,
        "OFFER_PROMOTION": offer or "special offer",
        "CAMPAIGN_FOCUS": objective or f"growing {industry} leads",
        "HOOK_FRAMEWORKS": hooks_fw or "pattern interrupt",
        "NOTES_FOR_AI": notes or f"Focus on {industry} pain points and {brand} solution.",
        "CTA": cta,
        "ASPECT_RATIO": aspect,
        "HOOK_ONSCREEN": hook_onscreen,
        "HOOK_VO": hook_vo,
        "PROBLEM_ONSCREEN": problem_onscreen,
        "PROBLEM_VO": problem_vo,
        "SOLUTION_ONSCREEN": solution_onscreen,
        "SOLUTION_VO": solution_vo,
        "PROOF_ONSCREEN": proof_onscreen,
        "PROOF_VO": proof_vo,
        "CTA_ONSCREEN": cta_onscreen,
        "CTA_VO": cta_vo,
    }


def _load_template() -> str:
    if TEMPLATE_PATH.is_file():
        return TEMPLATE_PATH.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Missing skeleton template: {TEMPLATE_PATH}")


def render_skeleton(context: dict[str, str]) -> str:
    text = _load_template()
    for key, value in context.items():
        text = text.replace(f"{{{{{key}}}}}", str(value))
    return text


def extract_heygen_spoken_script(skeleton_text: str, *, target_seconds: int = 30) -> str:
    """Concatenate Avatar Speaks + VO lines in story order."""
    parts: list[str] = []
    for match in _SPOKEN_BLOCK.finditer(skeleton_text):
        line = " ".join(match.group(1).strip().split())
        if line:
            parts.append(line.rstrip("."))
    spoken = ". ".join(parts)
    if spoken and not spoken.endswith((".", "!", "?")):
        spoken += "."
    if not spoken.strip():
        spoken = skeleton_text
        spoken = re.sub(r"\[(?:\d+–\d+|\d+-\d+)[^\]]*\][^\n]*", "", spoken, flags=re.I)
        spoken = re.sub(r"(Scene Direction|On-Screen Text|Avatar Attire|Background):[^\n]*", "", spoken, flags=re.I)
        spoken = " ".join(spoken.split())

    words_budget = max(12, int(target_seconds * WPS))
    words = spoken.split()
    if len(words) > words_budget:
        spoken = " ".join(words[:words_budget])
        if not spoken.endswith((".", "!", "?")):
            spoken += "."
    return spoken.strip()


def parse_spoken_lines(text: str, *, duration: int = 30) -> list[tuple[str, str, str]]:
    """Timed [MM:SS - MM:SS] lines, or chunk plain script into ~5 beats."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return []

    timed = list(_TIMED_LINE.finditer(text))
    if timed:
        return [
            (m.group(1), m.group(2), " ".join(m.group(3).split()))
            for m in timed
            if m.group(3).strip()
        ]

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw) if s.strip()]
    if not sentences:
        sentences = [raw]

    beat_count = 5
    per = max(1, (len(sentences) + beat_count - 1) // beat_count)
    chunks: list[str] = []
    for i in range(0, len(sentences), per):
        chunks.append(" ".join(sentences[i : i + per]))

    sec_per = max(3, duration // max(len(chunks), 1))
    lines: list[tuple[str, str, str]] = []
    t = 0
    for chunk in chunks:
        end = min(duration, t + sec_per)
        lines.append(
            (
                f"{t // 60:02d}:{t % 60:02d}",
                f"{end // 60:02d}:{end % 60:02d}",
                chunk,
            )
        )
        t = end
    return lines


_INSERT_STAT_PLACEHOLDER = re.compile(r"\[INSERT\b[^\]]*STAT\s*IMAGE[^\]]*\]", re.IGNORECASE)
_NUMBERED_INSERT_STAT = re.compile(
    r"\[INSERT\s+STAT\s+IMAGE\s*(\d+)\]", re.IGNORECASE
)
MIN_STAT_SLIDE_SEC = 3.5   # minimum seconds each image is visible
MAX_STAT_SLIDE_SEC = 5.5   # maximum seconds each image is visible (prevents long holds)


def parse_broll_stat_insert_cues(
    broll_script: str,
    *,
    duration: int = 30,
) -> list[dict[str, Any]]:
    """
    Stat-image cues from B-roll lines — handles markers embedded in scene visuals
    e.g. [00:36-00:42] PROOF — Presenter on camera [INSERT STAT IMAGE 1] ...
    """
    cues: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in (broll_script or "").splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        if not _INSERT_STAT_PLACEHOLDER.search(line):
            continue

        start_sec: float | None = None
        end_sec: float | None = None
        m = _SCENE_BROLL_RANGE.match(line)
        if m:
            start_sec = float(_timestamp_to_seconds(m.group("start")))
            end_sec = float(_timestamp_to_seconds(m.group("end")))
        else:
            for j in range(i + 1, len(lines)):
                m2 = _SCENE_BROLL_RANGE.match(lines[j])
                if m2:
                    start_sec = float(_timestamp_to_seconds(m2.group("start")))
                    end_sec = float(_timestamp_to_seconds(m2.group("end")))
                    break

        if start_sec is None:
            continue
        if end_sec is None or end_sec <= start_sec:
            end_sec = min(float(duration), start_sec + MIN_STAT_SLIDE_SEC)

        numbered = list(_NUMBERED_INSERT_STAT.finditer(line))
        if numbered:
            for match in numbered:
                cues.append(
                    {
                        "image_index": int(match.group(1)) - 1,
                        "start": start_sec,
                        "end": min(float(end_sec), float(duration)),
                    }
                )
        else:
            cues.append(
                {
                    "image_index": len(cues),
                    "start": start_sec,
                    "end": min(float(end_sec), float(duration)),
                }
            )
    return cues


def _extend_stat_segment(start: float, end: float, duration: float) -> tuple[float, float]:
    """Clamp each stats slide to [MIN_STAT_SLIDE_SEC, MAX_STAT_SLIDE_SEC]."""
    s = max(0.0, float(start))
    e = min(float(duration), float(end))
    span = e - s
    if span < MIN_STAT_SLIDE_SEC:
        mid = (s + e) / 2.0
        half = MIN_STAT_SLIDE_SEC / 2.0
        s = max(0.0, mid - half)
        e = min(float(duration), s + MIN_STAT_SLIDE_SEC)
    if e - s > MAX_STAT_SLIDE_SEC:
        # Keep start anchor, trim the tail
        e = min(float(duration), s + MAX_STAT_SLIDE_SEC)
    return s, e


def detect_insert_stat_segments(
    spoken_script: str,
    *,
    duration: int = 30,
) -> list[tuple[float, float]]:
    """Time windows for [INSERT … STAT IMAGE] placeholder lines in the approved script."""
    lines = parse_spoken_lines(spoken_script, duration=duration)
    segments: list[tuple[float, float]] = []
    for start, end, say in lines:
        if _INSERT_STAT_PLACEHOLDER.search(say) or re.match(r"^\s*\[INSERT\b", say, re.I):
            s = float(_timestamp_to_seconds(start))
            e = float(min(_timestamp_to_seconds(end), duration))
            if e <= s:
                e = min(float(duration), s + MIN_STAT_SLIDE_SEC)
            segments.append(_extend_stat_segment(s, e, float(duration)))
    return segments


def detect_insert_stat_segments_by_image_index(
    spoken_script: str,
    stats_count: int,
    *,
    duration: int = 30,
) -> list[tuple[float, float] | None]:
    """Map each stat image index to its [INSERT STAT IMAGE N] voice beat timestamp."""
    lines = parse_spoken_lines(spoken_script, duration=duration)
    result: list[tuple[float, float] | None] = [None] * stats_count
    for start, end, say in lines:
        m = re.search(r"\[INSERT\s+STAT\s+IMAGE\s+(\d+)\]", say, re.I)
        if not m:
            continue
        idx = int(m.group(1)) - 1
        if 0 <= idx < stats_count:
            s = float(_timestamp_to_seconds(start))
            e = float(min(_timestamp_to_seconds(end), duration))
            if e <= s:
                e = min(float(duration), s + MIN_STAT_SLIDE_SEC)
            result[idx] = _extend_stat_segment(s, e, float(duration))
    return result


# Match spoken lines that are PROOF BEAT lines — where the presenter is
# citing results, statistics, or client outcomes.
# Two tiers:
#   Tier 1 (strong): explicit metric keywords that mean "results section"
#   Tier 2 (supporting): client-achievement language that sits in the proof beat
# We deliberately DO NOT match: "results-driven", "leading solution", "leads to", etc.
_PROOF_LINE = re.compile(
    # Tier 1 — metric / stat keywords that only appear in proof beats
    r"\broas\b|\broi\b|\bcpa\b|\bcost[\s-]per[\s-](?:click|lead|acquisition|result)\b"
    r"|\bconversion rate\b|\bclick[\s-]through rate\b|\bctr\b"
    r"|\breturn on ad spend\b"
    # Explicit numbers with metric units (e.g. "4x", "320%", "$12k")
    r"|\b\d+\s*(?:x|×)\s*(?:roas|roi|return|revenue|result)"
    r"|\b\d+\s*%\s*(?:increase|improvement|more|better|reduction|growth|higher|lower|roi|roas|conversion)"
    r"|\$\s*\d[\d,.]+\s*(?:k|m|billion|million)?\s*(?:in\s+)?(?:revenue|profit|return|sales|savings)"
    # Tier 2 — proof-beat narrative language
    r"|\b(?:our\s+)?(?:clients?|customers?|businesses?)\s+(?:have\s+)?(?:achieved?|seen|experienced?|generated?|delivered?)\b"
    r"|\b(?:achieve|generate|deliver)ed?\s+.{0,30}(?:result|growth|revenue|profit|leads?|roi|roas)\b"
    r"|\bthe\s+(?:results?|numbers?|stats?|data|proof|figures?)\s+(?:speak|are|show)\b"
    r"|\bproven\s+(?:results?|track\s+record|system)\b"
    r"|\bcase\s+stud(?:y|ies)\b"
    # [INSERT STAT IMAGE] placeholder injected by script-writing LLM
    r"|\[INSERT\s+STAT",
    re.IGNORECASE,
)


def resolve_stats_image_urls(brief: dict | None) -> list[str]:
    """All uploaded stats dashboard URLs (supports legacy single URL)."""
    if not brief:
        return []
    kb = _kb(brief)
    urls: list[str] = []
    multi = kb.get("stats_image_urls")
    if isinstance(multi, list):
        for item in multi:
            u = str(item or "").strip()
            if u and u not in urls:
                urls.append(u)
    single = str(kb.get("stats_image_url") or brief.get("stats_image_url") or "").strip()
    if single and single not in urls:
        urls.insert(0, single)
    return urls


def resolve_stats_image_url(brief: dict | None) -> str | None:
    urls = resolve_stats_image_urls(brief)
    return urls[0] if urls else None


def _timestamp_to_seconds(ts: str) -> int:
    ts = (ts or "").strip()
    if ":" in ts:
        parts = ts.split(":", 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]) * 60 + int(parts[1])
    if ts.isdigit():
        return int(ts)
    return 0


def script_has_timed_lines(text: str) -> bool:
    """True when the script contains [MM:SS - MM:SS] spoken lines."""
    return bool(_TIMED_LINE.search(text or ""))


def resolve_timed_script_for_stats_overlay(
    brief: dict | None,
    result: dict | None = None,
) -> str:
    """Approved voice script WITH timestamps (+ B-roll stat cues when voice lacks them)."""
    brief = brief or {}
    result = result or {}
    kb = _kb(brief)

    voice = ""
    for src in (
        brief.get("avatar_script"),
        kb.get("avatar_script"),
        result.get("avatar_script"),
    ):
        text = str(src or "").strip()
        if text and script_has_timed_lines(text):
            voice = text
            break

    broll = _heygen_scene_broll_raw(brief)
    if voice and broll:
        return merge_voice_and_broll_timeline(voice, broll)
    if voice:
        return voice

    for src in (
        brief.get("video_script_skeleton"),
        kb.get("video_script_skeleton"),
        result.get("production_skeleton"),
    ):
        text = str(src or "").strip()
        if text and script_has_timed_lines(text):
            return text
    return ""


def merge_voice_and_broll_timeline(voice_script: str, broll_script: str) -> str:
    """Merge voice + B-roll into one timed script for stats/sync (inject stat markers from B-roll)."""
    voice = (voice_script or "").strip()
    broll = (broll_script or "").strip()
    if not voice:
        return voice
    if not broll or _INSERT_STAT_PLACEHOLDER.search(voice):
        return voice
    return inject_stat_markers_from_broll_into_timed_script(voice, broll)


def inject_stat_markers_from_broll_into_timed_script(
    voice_script: str,
    broll_script: str,
) -> str:
    """When B-roll has [INSERT STAT IMAGE N] but voice script does not, attach to matching beat."""
    if _INSERT_STAT_PLACEHOLDER.search(voice_script):
        return voice_script

    cues = parse_broll_stat_insert_cues(broll_script)
    if not cues:
        return voice_script

    out: list[str] = []
    for line in voice_script.splitlines():
        m = _TIMED_LINE.search(line)
        if not m:
            out.append(line)
            continue
        v_start = float(_timestamp_to_seconds(m.group(1)))
        v_end = float(_timestamp_to_seconds(m.group(2)))
        say = m.group(3).strip()
        for cue in cues:
            cs = float(cue["start"])
            ce = float(cue["end"])
            # Match by overlapping beat window — B-roll and voice timestamps rarely align to the exact second.
            overlaps = v_start <= cs < v_end or cs <= v_start < ce
            if not overlaps:
                continue
            marker = f"[INSERT STAT IMAGE {cue['image_index'] + 1}]"
            if marker.lower() not in say.lower():
                say = f"{marker} {say}"
        out.append(f"[{m.group(1)} - {m.group(2)}] {say}")
    return "\n".join(out)


def detect_insert_stat_segments_from_broll(
    broll_script: str,
    *,
    duration: int = 30,
) -> list[tuple[float, float]]:
    """Time windows for [INSERT STAT IMAGE] cues in the B-roll map."""
    cues = parse_broll_stat_insert_cues(broll_script, duration=duration)
    if not cues:
        return []
    ordered = sorted(cues, key=lambda c: (c["image_index"], c["start"]))
    return [
        _extend_stat_segment(float(c["start"]), float(c["end"]), float(duration))
        for c in ordered
    ]


def _line_is_proof_beat(text: str) -> bool:
    return bool(_PROOF_LINE.search(text or ""))


def detect_stats_proof_window(
    spoken_script: str,
    *,
    duration: int = 30,
    broll_script: str = "",
) -> tuple[float, float]:
    """Return the proof-beat time window driven by timed spoken lines in the script."""
    merged = spoken_script
    if broll_script.strip():
        merged = merge_voice_and_broll_timeline(spoken_script, broll_script)

    if not script_has_timed_lines(merged) and not broll_script.strip():
        proof_start = float(duration) * 0.90
        proof_end = min(float(duration), proof_start + 8.0)
        return proof_start, proof_end

    insert = detect_insert_stat_segments(merged, duration=duration) if script_has_timed_lines(merged) else []
    if not insert and broll_script.strip():
        insert = detect_insert_stat_segments_from_broll(broll_script, duration=duration)
    if insert:
        start = min(s for s, _ in insert)
        end = max(e for _, e in insert)
        return float(start), float(min(end, duration))

    segments = detect_stats_proof_segments(merged, duration=duration) if script_has_timed_lines(merged) else []
    if segments:
        start = min(s for s, _ in segments)
        end = max(e for _, e in segments)
        return float(start), float(min(end, duration))

    proof_start = float(duration) * 0.90
    proof_end = min(float(duration), proof_start + 8.0)
    return proof_start, proof_end


def detect_stats_proof_segments(
    spoken_script: str,
    *,
    duration: int = 30,
) -> list[tuple[float, float]]:
    """One time range per proof beat — pairs each stats image to the line it supports."""
    lines = parse_spoken_lines(spoken_script, duration=duration)
    segments: list[tuple[float, float]] = []
    for start, end, say in lines:
        if _line_is_proof_beat(say):
            s = float(_timestamp_to_seconds(start))
            e = float(min(_timestamp_to_seconds(end), duration))
            if e > s:
                segments.append((s, e))
    return segments


def pair_stats_image_segments(
    stats_count: int,
    spoken_script: str,
    *,
    duration: int = 30,
    broll_script: str = "",
) -> list[tuple[float, float]]:
    """Map each stats image to proof beats — merges voice script + B-roll INSERT cues."""
    if stats_count < 1:
        return []

    merged = spoken_script
    if broll_script.strip():
        merged = merge_voice_and_broll_timeline(spoken_script, broll_script)

    candidates: list[tuple[float, float]] = []
    if script_has_timed_lines(merged):
        insert = detect_insert_stat_segments(merged, duration=duration)
        proof = detect_stats_proof_segments(merged, duration=duration)
        candidates = insert if insert else proof
    elif broll_script.strip():
        candidates = detect_insert_stat_segments_from_broll(broll_script, duration=duration)
    else:
        logger.warning(
            "Stats overlay: script has no [MM:SS] timestamps — using end-of-video fallback"
        )

    broll_cues = (
        parse_broll_stat_insert_cues(broll_script, duration=duration)
        if broll_script.strip()
        else []
    )

    # Best path: one segment per image index from numbered INSERT markers in voice script.
    by_index = detect_insert_stat_segments_by_image_index(
        merged, stats_count, duration=duration
    )
    if all(seg is not None for seg in by_index):
        return [seg for seg in by_index if seg is not None]

    if broll_cues and stats_count > 0:
        by_index: dict[int, tuple[float, float]] = {}
        for cue in sorted(broll_cues, key=lambda c: (c["image_index"], c["start"])):
            idx = int(cue["image_index"])
            if 0 <= idx < stats_count and idx not in by_index:
                by_index[idx] = _extend_stat_segment(
                    float(cue["start"]), float(cue["end"]), float(duration)
                )
        if by_index:
            result: list[tuple[float, float]] = []
            for i in range(stats_count):
                if i in by_index:
                    result.append(by_index[i])
                elif candidates:
                    ci = min(i, len(candidates) - 1)
                    s, e = candidates[ci]
                    result.append(_extend_stat_segment(s, e, float(duration)))
                else:
                    break
            if len(result) == stats_count:
                return result

    if candidates:
        # Pair each image to its own candidate beat; if fewer beats than images,
        # reuse the last beat for the overflow images.
        result: list[tuple[float, float]] = []
        for i in range(stats_count):
            idx = min(i, len(candidates) - 1)
            s, e = candidates[idx]
            # Each image gets a clean, capped window starting right after the previous
            offset = (i - idx) * MAX_STAT_SLIDE_SEC
            seg_start = s + offset
            seg_end = seg_start + MAX_STAT_SLIDE_SEC
            result.append(_extend_stat_segment(seg_start, seg_end, float(duration)))
        return result

    # --- Step 3: last-resort fallback — final 15 % of video only ---
    # We have NO proof lines in this script. Show images briefly near the end.
    fallback_start = float(duration) * 0.85
    total = stats_count * MAX_STAT_SLIDE_SEC
    fallback_end = min(float(duration) * 0.98, fallback_start + total)

    seg = (fallback_end - fallback_start) / stats_count
    return [
        _extend_stat_segment(
            fallback_start + i * seg,
            fallback_start + (i + 1) * seg,
            float(duration),
        )
        for i in range(stats_count)
    ]


def _stat_headline_label(stats: Any) -> str:
    if not stats:
        return ""
    if isinstance(stats, dict):
        return str(
            stats.get("headline_stat") or stats.get("roas") or stats.get("industry") or ""
        ).strip()
    return str(
        getattr(stats, "headline_stat", "")
        or getattr(stats, "roas", "")
        or getattr(stats, "industry", "")
        or ""
    ).strip()


_GENERIC_STAT_WORDS = frozenset({
    "million", "billion", "thousand", "results", "revenue", "sales", "growth",
    "cost", "value", "total", "month", "week", "year", "from", "with", "over",
    "under", "into", "your", "their", "this", "that", "have", "been", "were",
})


def _numeric_signatures(headline: str) -> list[str]:
    """Distinctive numeric fragments from a stat label (e.g. 237, 2.43)."""
    sigs: list[str] = []
    for m in re.finditer(r"[\d,]+(?:\.\d+)?", headline or ""):
        num = m.group(0).replace(",", "")
        if len(num) >= 3:
            sigs.append(num)
        elif len(num) >= 1 and re.search(r"[$%]|[kmxb]\b", headline, re.I):
            sigs.append(num)
    seen: set[str] = set()
    out: list[str] = []
    for s in sigs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _spoken_cites_stat(spoken: str, headline: str) -> bool:
    """True when spoken line cites a distinctive figure from the stat headline."""
    if not headline.strip():
        return False
    spoken_norm = spoken.lower().replace(",", "").replace(" ", "")
    head_l = headline.lower()
    sigs = _numeric_signatures(headline)
    if sigs:
        hits = sum(1 for s in sigs if s in spoken_norm)
        if hits >= 2:
            return True
        if hits == 1 and len(sigs[0]) >= 3:
            return True
        if hits == 1 and re.search(r"[$%]|[kmxb]\b", headline, re.I):
            return True
    for word in re.findall(r"[a-z]{4,}", head_l):
        if word in _GENERIC_STAT_WORDS:
            continue
        if word in spoken.lower():
            return True
    return False


def build_master_production_timeline(
    voice_script: str,
    broll_script: str,
    *,
    duration: int = 60,
    stats_per_image: list[Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Unified beat map: voice + B-roll visual + stat image per timestamp."""
    warnings: list[str] = []
    stats_list = stats_per_image or []
    stat_labels = [_stat_headline_label(s) for s in stats_list]

    merged = merge_voice_and_broll_timeline(voice_script, broll_script)
    voice_lines = parse_spoken_lines(merged, duration=duration)
    broll_segments = parse_scene_broll_directions(broll_script, duration=duration)

    if not voice_lines:
        warnings.append("No timed voice script — add [MM:SS - MM:SS] lines in step 1.")
        return [], warnings

    beats: list[dict[str, Any]] = []

    for start, end, say in voice_lines:
        start_sec = float(_timestamp_to_seconds(start))
        end_sec = float(_timestamp_to_seconds(end))
        visual = _visual_for_time_range(start_sec, end_sec, broll_segments) or (
            "Presenter on camera"
        )

        insert_m = re.search(r"\[INSERT\s+STAT\s+IMAGE\s+(\d+)\]", say, re.I)
        visual_insert_m = re.search(r"\[INSERT\s+STAT\s+IMAGE\s+(\d+)\]", visual or "", re.I)
        stat_image: str | None = None
        stat_headline: str | None = None
        stat_warning: str | None = None

        spoken_clean = re.sub(r"\[INSERT\b[^\]]*\]\s*", "", say, flags=re.I).strip()

        if insert_m:
            idx = int(insert_m.group(1)) - 1
            stat_image = f"Stat image {idx + 1} on screen"
            stat_headline = stat_labels[idx] if idx < len(stat_labels) else None
            if idx < len(stats_list):
                from app.services.stats_image_service import (
                    performance_stats_to_context,
                    spoken_line_matches_stats,
                )

                st = stats_list[idx]
                ctx = performance_stats_to_context(st) if isinstance(st, dict) else st
                if ctx and not spoken_line_matches_stats(spoken_clean, ctx):
                    stat_warning = (
                        f"Voice should cite dashboard {idx + 1} figures "
                        f"({stat_headline or 'see OCR'}) while this image is on screen"
                    )
                    warnings.append(f"{start}: {stat_warning}")
            elif stat_headline and not _spoken_cites_stat(spoken_clean, stat_headline):
                stat_warning = (
                    f"Voice should cite '{stat_headline}' while this image is on screen"
                )
                warnings.append(f"{start}: {stat_warning}")
        elif visual_insert_m:
            idx = int(visual_insert_m.group(1)) - 1
            stat_image = f"Stat image {idx + 1} on screen"
            stat_headline = stat_labels[idx] if idx < len(stat_labels) else None
            if idx < len(stats_list):
                from app.services.stats_image_service import spoken_line_matches_stats

                st = stats_list[idx]
                ctx = st
                if isinstance(st, dict):
                    from app.services.stats_image_service import performance_stats_to_context

                    ctx = performance_stats_to_context(st)
                if ctx and not spoken_line_matches_stats(spoken_clean, ctx):
                    stat_warning = (
                        f"Voice should cite dashboard {idx + 1} while "
                        f"[INSERT STAT IMAGE {idx + 1}] is on screen (B-roll cue)"
                    )
                    warnings.append(f"{start}: {stat_warning}")
            elif stat_headline and not _spoken_cites_stat(spoken_clean, stat_headline):
                stat_warning = (
                    f"Voice should cite '{stat_headline}' while this image is on screen "
                    f"(B-roll has [INSERT STAT IMAGE {idx + 1}] here)"
                )
                warnings.append(f"{start}: {stat_warning}")

        beats.append(
            {
                "start": start,
                "end": end,
                "spoken": spoken_clean,
                "visual": visual,
                "stat_image": stat_image,
                "stat_headline": stat_headline,
                "stat_warning": stat_warning,
            }
        )

    if stats_list and not any(b.get("stat_image") for b in beats):
        warnings.append(
            "Stats images uploaded but no [INSERT STAT IMAGE N] in voice or B-roll — "
            "regenerate voice script after Re-extract stats."
        )
    elif stats_list:
        assigned = sum(1 for b in beats if b.get("stat_image"))
        if assigned < len(stats_list):
            warnings.append(
                f"Only {assigned} of {len(stats_list)} stat images are mapped — "
                "regenerate voice script so each dashboard gets one proof line."
            )

    if broll_script.strip() and not broll_segments:
        warnings.append("B-roll text present but could not parse timestamps — check format.")

    ready = bool(voice_lines) and (not broll_script.strip() or bool(broll_segments))
    return beats, warnings


_NUMBER_WORDS = (
    "hundred", "thousand", "million", "billion", "percent", "per cent",
    "times", "roas", "roi", "x roas", "x roi",
)


def _extract_proof_sentences(spoken_script: str) -> list[str]:
    """Spoken sentences that carry hard figures (%, $, digits, ROAS/million …).

    These are the exact lines the presenter MUST speak so the OCR proof numbers
    are never paraphrased or dropped by the generative Video Agent.
    """
    text = strip_insert_stat_placeholders(spoken_script or "")
    text = re.sub(r"\[\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    # Split on sentence boundaries; keep it simple and robust.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        low = s_clean.lower()
        has_symbol = bool(re.search(r"[\d]|%|\$", s_clean))
        has_word = any(w in low for w in _NUMBER_WORDS)
        if has_symbol or has_word:
            if s_clean not in out:
                out.append(s_clean)
    return out


def build_mandatory_spoken_figures_block(spoken_script: str) -> str:
    """Force HeyGen v3 to speak OCR proof numbers — works with or without stat-image overlay."""
    proof_sentences = _extract_proof_sentences(spoken_script)
    if not proof_sentences:
        return ""
    joined = " ".join(f'"{p}"' for p in proof_sentences)
    return (
        "MANDATORY SPOKEN FIGURES — HIGHEST PRIORITY (do NOT paraphrase, skip, "
        "round, shorten, or summarise): the presenter MUST say each of these exact "
        "sentences out loud, word-for-word, including every number, %, $ and ROAS "
        f"figure: {joined} "
        "These proof numbers are the entire point of the ad. If any figure is "
        "reworded or missing from the spoken audio, the video is wrong and rejected. "
        "Say the numbers exactly as written before moving on.\n"
    )


def build_stats_image_heygen_block(
    brief: dict,
    spoken_script: str,
    *,
    duration: int = 30,
) -> str:
    """OCR figures block + optional post overlay instructions for dashboard cards."""
    must_say = build_mandatory_spoken_figures_block(spoken_script)
    urls = resolve_stats_image_urls(brief)
    if not urls:
        return must_say

    start, end = detect_stats_proof_window(spoken_script, duration=duration)
    overlay = (
        "STATS DASHBOARD (added in post-production — NOT in HeyGen output):\n"
        f"Dashboard screenshot(s) are inserted after render (~{start:.0f}s–{end:.0f}s). "
        "Keep the presenter full frame on camera for the ENTIRE video. "
        "Never overlay, picture-in-picture, zoom, corner-box, or full-screen any stats, charts, "
        "dashboards, or performance graphics. [INSERT STAT IMAGE] markers are silent post cues only.\n"
    )
    return must_say + overlay


def _heygen_visual_cues(brief: dict) -> str:
    raw = brief.get("heygen_settings")
    if isinstance(raw, dict):
        return str(raw.get("visual_cues") or "").strip()
    kb = _kb(brief)
    if isinstance(kb.get("heygen_settings"), dict):
        return str(kb["heygen_settings"].get("visual_cues") or "").strip()
    return ""


def _heygen_settings_dict(brief: dict | None) -> dict:
    if not brief:
        return {}
    raw = brief.get("heygen_settings")
    if isinstance(raw, dict):
        return raw
    kb = _kb(brief)
    if isinstance(kb.get("heygen_settings"), dict):
        return kb["heygen_settings"]
    return {}


def _heygen_scene_broll_raw(brief: dict | None) -> str:
    heygen = _heygen_settings_dict(brief)
    return str(heygen.get("scene_broll_directions") or "").strip()


def _broll_is_directed(brief: dict | None) -> bool:
    """Return True only when there are actual scene directions to follow.

    Rationale: "directed" mode tells HeyGen to use ONLY the listed visuals and
    suppresses all automatic B-roll selection.  Activating it without any
    directions causes every spoken line to fall back to "Presenter on camera"
    (no B-roll at all).  We therefore require real direction text to exist.
    """
    heygen = _heygen_settings_dict(brief)
    has_directions = bool(_heygen_scene_broll_raw(brief))
    mode = str(heygen.get("broll_insert") or "").strip().lower()
    # Only lock HeyGen into directed mode when the user has actually written scenes
    if mode == "directed":
        return has_directions
    # Any other non-empty mode that still has directions → also treat as directed
    return has_directions


_DASH = r"[-–—:]"
_SCENE_BROLL_RANGE = re.compile(
    rf"^\[?(?P<start>\d{{1,2}}:\d{{2}})\s*{_DASH}\s*(?P<end>\d{{1,2}}:\d{{2}})\]?\s*"
    rf"(?:(?P<label>HOOK|PROBLEM|SOLUTION|PROOF|CTA)\s*{_DASH}?\s*)?"
    rf"(?P<visual>.+)$",
    re.IGNORECASE,
)
_SCENE_BROLL_AT = re.compile(
    rf"^(?P<at>\d{{1,2}}:\d{{2}})\s*{_DASH}\s*"
    rf"(?:(?P<label>HOOK|PROBLEM|SOLUTION|PROOF|CTA)\s*{_DASH}?\s*)?"
    rf"(?P<visual>.+)$",
    re.IGNORECASE,
)
_SCENE_BROLL_BEAT = re.compile(
    rf"^(?P<label>HOOK|PROBLEM|SOLUTION|PROOF|CTA)\s*{_DASH}\s*(?P<visual>.+)$",
    re.IGNORECASE,
)

_BEAT_ORDER = ("HOOK", "PROBLEM", "SOLUTION", "PROOF", "CTA")


def parse_scene_broll_directions(
    raw: str,
    *,
    duration: int = 30,
) -> list[dict[str, Any]]:
    """
  Parse user scene B-roll map.
  Formats:
    [00:00-00:08] HOOK — Presenter on camera, modern office
    00:08 — B-roll: laptop analytics dashboard scrolling
    PROBLEM — B-roll: frustrated CEO at desk
    """
    segments: list[dict[str, Any]] = []
    beat_only: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        m = _SCENE_BROLL_RANGE.match(text)
        if m:
            start = float(_timestamp_to_seconds(m.group("start")))
            end = float(_timestamp_to_seconds(m.group("end")))
            if end <= start:
                end = min(float(duration), start + 4.0)
            segments.append(
                {
                    "start": start,
                    "end": min(end, float(duration)),
                    "label": (m.group("label") or "").upper() or None,
                    "visual": m.group("visual").strip(),
                }
            )
            continue
        m = _SCENE_BROLL_AT.match(text)
        if m:
            start = float(_timestamp_to_seconds(m.group("at")))
            segments.append(
                {
                    "start": start,
                    "end": min(float(duration), start + 5.0),
                    "label": (m.group("label") or "").upper() or None,
                    "visual": m.group("visual").strip(),
                }
            )
            continue
        m = _SCENE_BROLL_BEAT.match(text)
        if m:
            beat_only.append(
                {
                    "label": m.group("label").upper(),
                    "visual": m.group("visual").strip(),
                }
            )
    if segments:
        return segments
    if beat_only:
        n = len(beat_only)
        seg_len = float(duration) / max(n, 1)
        for i, item in enumerate(beat_only):
            segments.append(
                {
                    "start": i * seg_len,
                    "end": min(float(duration), (i + 1) * seg_len),
                    "label": item["label"],
                    "visual": item["visual"],
                }
            )
    return segments


def _visual_for_time_range(
    start_sec: float,
    end_sec: float,
    segments: list[dict[str, Any]],
) -> str | None:
    """Return the visual for the B-roll segment that best covers this time range.

    Priority:
    1. Segment with highest overlap with [start_sec, end_sec].
    2. If no overlap at all, fall back to the closest segment by midpoint distance
       so spoken lines never silently lose their visual direction.
    """
    if not segments:
        return None
    mid = (start_sec + end_sec) / 2.0
    best: dict[str, Any] | None = None
    best_overlap = 0.0
    best_dist = float("inf")

    for seg in segments:
        s, e = float(seg["start"]), float(seg["end"])
        overlap = max(0.0, min(end_sec, e) - max(start_sec, s))
        if overlap > best_overlap:
            best_overlap = overlap
            best = seg
        elif overlap == 0.0:
            # No overlap — track nearest by midpoint distance as fallback
            seg_mid = (s + e) / 2.0
            dist = abs(mid - seg_mid)
            if dist < best_dist and best_overlap == 0.0:
                best_dist = dist
                best = seg

    return str(best["visual"]).strip() if best else None


def _broll_aspect_suffix(format_type: str) -> str:
    ft = (format_type or "").lower()
    if ft in {"reel", "stories"}:
        return " [9:16 vertical full-bleed — never landscape with black bars]"
    if ft == "video":
        return " [16:9 landscape full-bleed — never vertical with side bars]"
    return ""


def build_scene_broll_directions_block(
    brief: dict | None,
    *,
    duration: int = 30,
    format_type: str = "",
) -> str:
    """Mandatory scene-by-scene B-roll block for HeyGen when user directs visuals."""
    raw = _heygen_scene_broll_raw(brief)
    if not raw:
        return ""
    segments = parse_scene_broll_directions(raw, duration=duration)
    if not segments:
        return (
            "SCENE B-ROLL DIRECTIONS (mandatory — follow exactly, no random cuts):\n"
            f"{raw.strip()}\n"
        )
    rows = [
        "SCENE B-ROLL DIRECTIONS (mandatory — use these EXACT visuals per scene; "
        "do NOT improvise or pick random stock footage):"
    ]
    aspect_suffix = _broll_aspect_suffix(format_type)
    for seg in segments:
        label = f"{seg['label']} — " if seg.get("label") else ""
        start = int(seg["start"])
        end = int(seg["end"])
        visual = str(seg["visual"])
        if aspect_suffix and "presenter" not in visual.lower():
            visual = f"{visual}{aspect_suffix}"
        rows.append(
            f"[{start // 60:02d}:{start % 60:02d}–{end // 60:02d}:{end % 60:02d}] "
            f"{label}{visual}"
        )
    return "\n".join(rows)


def build_script_visual_sync_block(
    spoken_script: str,
    *,
    duration: int = 30,
    brief: dict | None = None,
    format_type: str = "",
) -> str:
    """Compact beat map: dialogue, visuals, and facial expression per spoken line."""
    spoken_script = strip_insert_stat_placeholders(spoken_script)
    lines = parse_spoken_lines(spoken_script, duration=duration)
    if not lines:
        return ""

    visual_cues = _heygen_visual_cues(brief or {})
    scene_broll_raw = _heygen_scene_broll_raw(brief)
    scene_segments = parse_scene_broll_directions(scene_broll_raw, duration=duration)
    directed = _broll_is_directed(brief)
    has_stats_image = bool(resolve_stats_image_urls(brief))
    aspect_suffix = _broll_aspect_suffix(format_type)
    total = len(lines)
    rows = [
        "SCRIPT-TO-VIDEO SYNC MAP (mandatory — dialogue, visuals, and expression must match each beat):"
    ]
    if directed:
        rows.insert(
            0,
            "Use ONLY the visuals listed below — never random B-roll or unrelated footage.",
        )
    for i, (start, end, say) in enumerate(lines):
        start_sec = float(_timestamp_to_seconds(start))
        end_sec = float(_timestamp_to_seconds(end))
        scene_visual = _visual_for_time_range(start_sec, end_sec, scene_segments)
        if has_stats_image and (
            _line_is_proof_beat(say)
            or _INSERT_STAT_PLACEHOLDER.search(say)
            or re.match(r"^\s*\[INSERT\b", say or "", re.I)
        ):
            visual = (
                "Presenter on camera full frame — speak to camera. "
                "Do not show stats dashboards or charts (added in post-production)."
            )
        elif scene_visual:
            visual = f"EXACT VISUAL (mandatory): {scene_visual}{aspect_suffix}"
        elif has_stats_image:
            visual = (
                "Presenter on camera full frame — no dashboard, chart, or corner stat overlay."
            )
        elif directed:
            visual = "Presenter on camera full frame — no unscripted B-roll."
        elif "hook" in say.lower()[:20] or start.endswith("00"):
            visual = "Presenter on camera, full frame, speaking this line."
        else:
            visual = (
                "B-roll OR presenter — visual must illustrate exactly what is said in this line."
                f"{aspect_suffix}"
            )
        if visual_cues and not scene_visual:
            visual += f" Also respect timed cues: {visual_cues[:200]}."
        expression = infer_avatar_expression_for_line(
            say, beat_index=i, total_beats=total
        )
        rows.append(
            f'[{start}–{end}] SAY: "{say}" | VISUAL: {visual} | EXPRESSION: {expression}'
        )
    return "\n".join(rows)


def align_skeleton_to_spoken_script(
    skeleton: str,
    spoken_script: str,
    *,
    duration: int = 30,
    brief: dict | None = None,
) -> str:
    """
    Rewrite Avatar Speaks / VO blocks to match approved script.
    Inject scene directions so B-roll matches each spoken beat.
    """
    lines = parse_spoken_lines(spoken_script, duration=duration)
    if not lines:
        return skeleton

    say_texts = [line[2] for line in lines]
    idx = 0

    def _replace_spoken(m: re.Match) -> str:
        nonlocal idx
        label = m.group(1)
        if idx < len(say_texts):
            body = say_texts[idx]
            idx += 1
            return f"{label}:\n{body}\n"
        return m.group(0)

    out = _SPOKEN_LABEL.sub(_replace_spoken, skeleton)

    scene_segments = parse_scene_broll_directions(
        _heygen_scene_broll_raw(brief), duration=duration
    )
    timed_lines = parse_spoken_lines(spoken_script, duration=duration)
    beat_idx = 0

    def _enhance_scene(m: re.Match) -> str:
        nonlocal beat_idx
        prefix = m.group(1)
        body = " ".join(m.group(2).split())
        if beat_idx < len(say_texts):
            say = say_texts[beat_idx]
            if beat_idx < len(timed_lines):
                t_start, t_end, _ = timed_lines[beat_idx]
                scene_visual = _visual_for_time_range(
                    float(_timestamp_to_seconds(t_start)),
                    float(_timestamp_to_seconds(t_end)),
                    scene_segments,
                )
            else:
                scene_visual = None
            beat_idx += 1
            if scene_visual:
                sync = (
                    f"MANDATORY VISUAL for this beat: {scene_visual}. "
                    f"Spoken line: \"{say}\". Do not substitute other B-roll. "
                )
            else:
                sync = (
                    f"B-roll and cuts must match this spoken beat only: \"{say}\". "
                    f"Avatar expression must match this line's emotion (no constant smile). "
                    "Do not show unrelated topics. "
                )
            if body and sync.lower() not in body.lower():
                body = f"{sync}{body}"
            else:
                body = sync + body
        return f"{prefix}\n{body}\n"

    out = _SCENE_DIRECTION.sub(_enhance_scene, out)
    logger.info(
        "Aligned production skeleton to spoken script (%s beats, %s words)",
        len(say_texts),
        len(spoken_script.split()),
    )
    return out


def build_higgsfield_motion_prompt(
    skeleton_text: str,
    *,
    brief: dict,
    copy: dict,
    format_type: str,
    duration: int,
) -> str:
    """Image-to-video motion prompt — no on-screen text (models render garbled letters)."""
    brand = brief.get("brand_name") or brief.get("product_name") or "brand"
    industry = brief.get("target_industry_label") or "business"
    ft = (format_type or "reel").lower()
    orient = "vertical 9:16" if ft in {"reel", "video", "stories"} else "landscape 16:9"

    prompt = (
        f"Animate the seed image as one continuous {orient} shot, about {duration} seconds. "
        f"Subtle cinematic camera movement only: slow push-in, gentle pan, or soft parallax. "
        f"Professional {industry} advertising look for {brand}, warm natural lighting, "
        "realistic skin tones, shallow depth of field. "
        "CRITICAL: absolutely no on-screen text, captions, subtitles, logos, watermarks, "
        "letters, signs, banners, or UI. No scene cuts, no morphing faces, no extra people. "
        "Keep the same subject and wardrobe as the seed image."
    )
    return clamp_runway_image_prompt(prompt, max_len=RUNWAY_VIDEO_PROMPT_MAX)


def build_veo_prompt_from_skeleton(
    skeleton_text: str,
    *,
    brief: dict,
    copy: dict,
    format_type: str,
    duration: int,
) -> str:
    """Condensed motion prompt for Runway image_to_video (Veo)."""
    brand = brief.get("brand_name") or brief.get("product_name") or "brand"
    industry = brief.get("target_industry_label") or "business"
    hook = copy.get("hook") or ""
    cta = copy.get("cta") or brief.get("cta") or "Learn more"
    spoken = extract_heygen_spoken_script(skeleton_text, target_seconds=duration)

    prompt = (
        f"Cinematic {duration}s vertical Meta {format_type} ad, 9:16, for {brand} ({industry}). "
        "0-3s: warm hook, presenter to camera. "
        "3-10s: fast full-frame pain-point cuts (natural skin tones on people, no blue/teal faces). "
        f"10-{duration}s: warm natural lighting, solution visuals, confident close. "
        f"On-screen hook: {hook}. "
        f"Voiceover theme: {spoken[:400]}. "
        f"End CTA: {cta}. "
        "Bold mobile subtitles, professional lighting, realistic—not cartoon."
    )
    return clamp_runway_image_prompt(prompt, max_len=RUNWAY_VIDEO_PROMPT_MAX)


def build_heygen_agent_prompt(
    *,
    brief: dict,
    copy: dict,
    format_type: str,
    duration: int,
    avatar_id: str,
    voice_id: str,
    spoken_script: str,
    production_skeleton: str,
) -> str:
    from app.services.heygen_prompt import (
        AVATAR_EXPRESSION_SYNC_RULE,
        BRAND_BADGE_FORBIDDEN_RULE,
        HEYGEN_IN_VIDEO_CAPTION_RULE,
        NATURAL_COLOR_RULE,
        SCRIPT_VISUAL_SYNC_RULE,
        AUSTRALIAN_HEYGEN_VOICE_RULE,
        _heygen_settings,
        brand_onscreen_text_rule,
        broll_orientation_rule,
        clamp_heygen_v3_prompt,
        resolve_aspect_ratio_label,
        resolve_background_direction,
        resolve_text_placement_rules,
        resolve_visual_style,
        sanitize_production_skeleton_for_heygen,
    )

    brand = brief.get("brand_name") or brief.get("product_name") or "the brand"
    tone = str(brief.get("ad_copy_tone") or "").strip()
    heygen = _heygen_settings(brief)
    aspect = resolve_aspect_ratio_label(heygen, format_type)
    background = resolve_background_direction(brief, heygen)
    visual_style = resolve_visual_style(
        brief, heygen, for_video_agent=True, format_type=format_type
    )

    logo_hint = ""
    if brief.get("logo_url") or format_type in {"reel", "video", "stories"}:
        corner = (
            "bottom-right corner"
            if format_type in {"reel", "stories"}
            else "top-left corner"
        )
        logo_hint = (
            f"Leave the {corner} clear for the {brand} logo watermark (added in post); "
            "do not draw a fake logo there. Keep face and bottom-centre captions unobstructed."
        )

    caption_hint = ""
    if heygen.get("captions", True) is not False and heygen.get("burn_in_captions", True) is not False:
        caption_hint = HEYGEN_IN_VIDEO_CAPTION_RULE
    pdf_only = is_pdf_script_mode(brief)
    stats_image_block = build_stats_image_heygen_block(
        brief, spoken_script, duration=duration
    )
    has_stats_image = bool(resolve_stats_image_urls(brief))
    sync_block = build_script_visual_sync_block(
        spoken_script, duration=duration, brief=brief, format_type=format_type
    )
    scene_broll_block = build_scene_broll_directions_block(
        brief, duration=duration, format_type=format_type
    )
    broll_directed = _broll_is_directed(brief)

    script_rule = (
        "Follow the spoken script verbatim; do not invent alternate dialogue. "
        "B-roll and on-screen text must match each spoken sentence."
        if pdf_only
        else (
            "The SPOKEN SCRIPT is the single source of truth for dialogue. "
            "Production script scene timings, B-roll, and on-screen text must illustrate "
            "exactly what is said in each beat — never unrelated footage. "
            "Avatar Speaks / VO lines in the production script must match the spoken script."
        )
    )

    portrait_rule = ""
    broll_orient = broll_orientation_rule(format_type)
    if format_type in {"reel", "stories"}:
        portrait_rule = (
            "Format: full-frame 9:16 vertical portrait (1080x1920). "
            "Subject and environment fill the frame edge-to-edge — no letterboxing or empty bars. "
        )
    elif format_type == "video":
        portrait_rule = (
            "Format: full-frame 16:9 landscape (1920x1080). "
            "Render the entire video in horizontal landscape — NOT vertical portrait. "
            "Presenter medium shot (head to mid-torso) framed for 16:9 width — never a tight "
            "vertical close-up cropped to fill landscape. "
            "Subject and environment fill the frame edge-to-edge — no windowboxing or empty bars. "
        )

    hook = copy.get("hook") or ""
    headline = copy.get("headline") or ""
    cta = copy.get("cta") or brief.get("cta") or "Learn more"

    approved_raw = str(brief.get("avatar_script") or _kb(brief).get("avatar_script") or "").strip()
    spoken_for_prompt = strip_insert_stat_placeholders(spoken_script.strip())
    spoken_for_prompt = re.sub(
        r"\[\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\]\s*", "", spoken_for_prompt
    )
    spoken_for_prompt = " ".join(spoken_for_prompt.split())
    # User-approved timed scripts must reach HeyGen in full — truncating drops proof/CTA beats.
    if not (approved_raw and script_has_timed_lines(approved_raw)):
        if len(spoken_for_prompt) > 2800:
            spoken_for_prompt = spoken_for_prompt[:2800].rsplit(" ", 1)[0] + "…"

    skeleton_excerpt = production_skeleton.strip()
    skeleton_excerpt = sanitize_production_skeleton_for_heygen(
        skeleton_excerpt, brand=str(brand), tone=tone or None
    )
    if len(skeleton_excerpt) > 5200:
        skeleton_excerpt = skeleton_excerpt[:5200].rsplit("\n", 1)[0] + "\n…"

    duration_rule = (
        f"HARD RUNTIME (mandatory): Final video MUST be {duration} seconds total — not {duration + 5}s, "
        f"not longer. Pace all scenes to finish by {duration}s. "
        f"Scene budget: 0–3s hook, 3–10s problem, 10–20s solution, 20–27s proof, 27–{duration}s CTA. "
        f"Shorten B-roll holds if needed; do not add extra scenes.\n"
    )

    mandatory_figures = build_mandatory_spoken_figures_block(spoken_script)

    prompt_parts = [
        *([f"{mandatory_figures}\n"] if mandatory_figures else []),
        f"Create a {duration}-second {format_type} video ad for {brand}.\n",
        f"{brand_onscreen_text_rule(str(brand), tone=tone or None)}\n",
        f"{BRAND_BADGE_FORBIDDEN_RULE}\n",
        f"{AVATAR_EXPRESSION_SYNC_RULE}\n",
        f"{AUSTRALIAN_HEYGEN_VOICE_RULE}\n",
        duration_rule,
        f"Aspect ratio: {aspect}. {portrait_rule}\n",
        f"{broll_orient}\n" if broll_orient else "",
        f"{BROLL_STATS_POSTPROCESS_RULES if has_stats_image else BROLL_FULL_FRAME_RULES}\n",
        *(
            [f"{HEYGEN_FORBID_STATS_GRAPHICS_RULE}\n"]
            if has_stats_image
            else []
        ),
        "Presenter: use the selected HeyGen avatar and voice (do not substitute a different person).\n",
        f"BACKGROUNDS (change per scene as the script dictates): {background}\n",
        f"VISUAL STYLE: {visual_style}\n",
        f"{SCRIPT_VISUAL_SYNC_RULE}\n",
        *([f"{BROLL_NO_RANDOM_RULE}\n"] if broll_directed else []),
        f"{script_rule}\n",
        f"SPOKEN SCRIPT (presenter must speak this exactly):\n{spoken_for_prompt}\n",
    ]
    if stats_image_block:
        prompt_parts.append(f"{stats_image_block}\n")
    if scene_broll_block:
        prompt_parts.append(f"{scene_broll_block}\n")
    if sync_block:
        prompt_parts.append(f"{sync_block}\n")
    prompt_parts.extend(
        [
            f"Ad hook: {hook}. Headline: {headline}. CTA: {cta}.\n",
            f"{resolve_text_placement_rules()}\n",
            f"{NATURAL_COLOR_RULE}\n",
            "PRODUCTION SCRIPT (timing, scene cuts, on-screen text, colour grade):\n",
            f"{skeleton_excerpt}\n",
            f"{caption_hint} {logo_hint}",
        ]
    )
    prompt = "".join(prompt_parts).strip()

    return clamp_heygen_v3_prompt(prompt)


async def _fill_skeleton_with_claude(
    *,
    brief: dict,
    copy: dict,
    rendered: str,
    context: dict[str, str],
) -> str | None:
    if not settings.OPENROUTER_API_KEY:
        return None
    from app.services.ai_service import ai_service

    approved = str(brief.get("avatar_script") or _kb(brief).get("avatar_script") or "").strip()
    user_payload = {
        "brief_context": context,
        "variant_copy": {
            "hook": copy.get("hook"),
            "headline": copy.get("headline"),
            "body_copy": copy.get("body_copy"),
            "cta": copy.get("cta"),
        },
        "draft_skeleton": rendered,
    }
    if approved and _kb(brief).get("script_source") != "skeleton":
        user_payload["approved_spoken_script"] = approved
    system = f"""You are a senior performance video scriptwriter for Australian Meta video ads.

{AUSTRALIAN_ENGLISH_SCRIPT_RULES}

Fill the production skeleton with concrete scene directions and spoken lines.
Keep all section headers and [timing] blocks exactly as in the draft.
If approved_spoken_script is provided, Avatar Speaks and VO lines MUST use those exact words
(split across sections in story order) — do not write different dialogue unless improving Aussie phrasing only.
Each Scene Direction must say what B-roll to show WHILE that beat is spoken (same topic).
Add "Avatar Expression:" under each talking-head beat — emotion must match the words (concerned for pain, no smile on problems, confident only on benefits, warm smile on CTA only).
On-screen text: short punchy mobile lines matching what is said in that beat.
Headlines in lower third during talking-head — never over the face.
On-screen brand text must use the exact BRAND name only — never prefix with tone words
(e.g. forbidden: "Professional ClickTrends" when brand is ClickTrends).
Never add persistent corner brand badges during B-roll.
FORBIDDEN: avatar smiling throughout the entire video — vary expression beat-by-beat per script.
All Avatar Speaks / VO dialogue: natural Australian English — not American.
Natural skin tones on people — never blue/teal faces.
B-ROLL: ONE full-frame shot per cut illustrating the spoken line for that beat.
No split-screen or half-chart layouts.
Return ONLY the completed plain-text script — no markdown fences, no JSON."""

    try:
        client = ai_service._get_client()
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            max_tokens=2500,
        )
        text = (response.choices[0].message.content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return text if len(text) > 200 else None
    except Exception:
        logger.exception("Claude skeleton fill failed")
        return None


async def ensure_production_skeleton(
    brief: dict,
    copy: dict | None = None,
    *,
    duration: int = 30,
    format_type: str = "reel",
    force_refresh: bool = False,
) -> str:
    """Build or return cached production skeleton for this brief."""
    copy = copy or {}
    kb = _kb(brief)
    if kb.get("script_source") in {"custom", "skeleton"}:
        custom = kb.get("video_script_skeleton") or kb.get("custom_prompt")
        if custom and str(custom).strip():
            return str(custom).strip()
    if not force_refresh:
        cached = kb.get("video_script_skeleton")
        version = str(kb.get("video_script_skeleton_version") or "")
        if cached and str(cached).strip() and version == SKELETON_VERSION:
            return str(cached).strip()

    context = build_skeleton_context(
        brief, copy, duration=duration, format_type=format_type
    )
    rendered = render_skeleton(context)
    filled = await _fill_skeleton_with_claude(
        brief=brief, copy=copy, rendered=rendered, context=context
    )
    result = (filled or rendered).strip()

    approved = str(brief.get("avatar_script") or kb.get("avatar_script") or "").strip()
    if approved and kb.get("script_source") != "skeleton":
        result = align_skeleton_to_spoken_script(
            result, approved, duration=duration, brief=brief
        )
    return result


def resolve_heygen_spoken_script(
    brief: dict,
    copy: dict,
    *,
    production_skeleton: str,
    target_seconds: int,
) -> str:
    """Priority: PDF script → manual avatar_script → skeleton VO → ad copy."""
    kb = _kb(brief)
    if is_pdf_script_mode(brief):
        pdf = kb.get("pdf_script_text") or brief.get("pdf_script_text")
        if pdf and str(pdf).strip():
            text = str(pdf).strip()
            text = re.sub(r"\[\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\]\s*", "", text)
            words_budget = max(12, int(target_seconds * WPS))
            words = text.split()
            return " ".join(words[:words_budget]) if len(words) > words_budget else text

    manual = brief.get("avatar_script") or kb.get("avatar_script")
    if manual and str(manual).strip() and kb.get("script_source") != "skeleton":
        raw_manual = str(manual).strip()
        text = strip_insert_stat_placeholders(raw_manual)
        text = re.sub(r"\[\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\]\s*", "", text)
        # A user-approved TIMED script is sized for this video — speak it in full.
        # Truncating here drops the proof/CTA lines at the end (stats never spoken).
        if script_has_timed_lines(raw_manual):
            return " ".join(text.split())
        words_budget = max(12, int(target_seconds * WPS))
        words = text.split()
        return " ".join(words[:words_budget]) if len(words) > words_budget else " ".join(text.split())

    spoken = extract_heygen_spoken_script(production_skeleton, target_seconds=target_seconds)
    if spoken.strip():
        return spoken

    words_budget = max(12, int(target_seconds * WPS))
    parts = [
        copy.get("hook", ""),
        copy.get("headline", ""),
        copy.get("body_copy", ""),
        f"{copy.get('cta') or brief.get('cta', 'Learn more')}.",
    ]
    script = " ".join(p for p in parts if p).strip()
    words = script.split()
    if len(words) > words_budget:
        script = " ".join(words[:words_budget])
    return script


def merge_skeleton_into_key_benefits(kb: dict, skeleton: str) -> dict:
    return {
        **kb,
        "video_script_skeleton": skeleton,
        "video_script_skeleton_version": SKELETON_VERSION,
    }
