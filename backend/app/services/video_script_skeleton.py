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
from app.services.heygen_prompt import BROLL_FULL_FRAME_RULES
from app.services.industries import resolve_target_industry

logger = logging.getLogger(__name__)

SKELETON_VERSION = "6"  # v6: no face banners, CEO/entrepreneur B-roll, subtitle burn

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


def _heygen_visual_cues(brief: dict) -> str:
    raw = brief.get("heygen_settings")
    if isinstance(raw, dict):
        return str(raw.get("visual_cues") or "").strip()
    kb = _kb(brief)
    if isinstance(kb.get("heygen_settings"), dict):
        return str(kb["heygen_settings"].get("visual_cues") or "").strip()
    return ""


def build_script_visual_sync_block(
    spoken_script: str,
    *,
    duration: int = 30,
    brief: dict | None = None,
) -> str:
    """Compact beat map: what is said + what must be on screen at that moment."""
    lines = parse_spoken_lines(spoken_script, duration=duration)
    if not lines:
        return ""

    visual_cues = _heygen_visual_cues(brief or {})
    rows = [
        "SCRIPT-TO-VIDEO SYNC MAP (mandatory — dialogue, B-roll, and text must match each beat):"
    ]
    for start, end, say in lines:
        visual = (
            "Presenter on camera, full frame, speaking this line."
            if "hook" in say.lower()[:20] or start.endswith("00")
            else "B-roll OR presenter — visual must illustrate exactly what is said in this line."
        )
        if visual_cues:
            visual += f" Also respect timed cues: {visual_cues[:200]}."
        rows.append(f'[{start}–{end}] SAY: "{say}" | VISUAL: {visual}')
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

    beat_idx = 0

    def _enhance_scene(m: re.Match) -> str:
        nonlocal beat_idx
        prefix = m.group(1)
        body = " ".join(m.group(2).split())
        if beat_idx < len(say_texts):
            say = say_texts[beat_idx]
            beat_idx += 1
            sync = (
                f"B-roll and cuts must match this spoken beat only: \"{say}\". "
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
        HEYGEN_IN_VIDEO_CAPTION_RULE,
        NATURAL_COLOR_RULE,
        SCRIPT_VISUAL_SYNC_RULE,
        _heygen_settings,
        clamp_heygen_v3_prompt,
        resolve_aspect_ratio_label,
        resolve_background_direction,
        resolve_text_placement_rules,
        resolve_visual_style,
    )

    brand = brief.get("brand_name") or brief.get("product_name") or "the brand"
    heygen = _heygen_settings(brief)
    aspect = resolve_aspect_ratio_label(heygen, format_type)
    background = resolve_background_direction(brief, heygen)
    visual_style = resolve_visual_style(brief, heygen, for_video_agent=True)

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
    sync_block = build_script_visual_sync_block(
        spoken_script, duration=duration, brief=brief
    )

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
    if format_type in {"reel", "stories"}:
        portrait_rule = (
            "Format: full-frame 9:16 vertical portrait (1080x1920). "
            "Subject and environment fill the frame edge-to-edge — no letterboxing or empty bars. "
        )
    elif format_type == "video":
        portrait_rule = (
            "Format: full-frame 16:9 landscape (1920x1080). "
            "Subject and environment fill the frame edge-to-edge — no letterboxing or empty bars. "
        )

    hook = copy.get("hook") or ""
    headline = copy.get("headline") or ""
    cta = copy.get("cta") or brief.get("cta") or "Learn more"

    spoken_for_prompt = spoken_script.strip()
    if len(spoken_for_prompt) > 2800:
        spoken_for_prompt = spoken_for_prompt[:2800].rsplit(" ", 1)[0] + "…"

    skeleton_excerpt = production_skeleton.strip()
    if len(skeleton_excerpt) > 5200:
        skeleton_excerpt = skeleton_excerpt[:5200].rsplit("\n", 1)[0] + "\n…"

    duration_rule = (
        f"HARD RUNTIME (mandatory): Final video MUST be {duration} seconds total — not {duration + 5}s, "
        f"not longer. Pace all scenes to finish by {duration}s. "
        f"Scene budget: 0–3s hook, 3–10s problem, 10–20s solution, 20–27s proof, 27–{duration}s CTA. "
        f"Shorten B-roll holds if needed; do not add extra scenes.\n"
    )

    prompt_parts = [
        f"Create a {duration}-second {format_type} video ad for {brand}.\n",
        duration_rule,
        f"Aspect ratio: {aspect}. {portrait_rule}\n",
        f"{BROLL_FULL_FRAME_RULES}\n"
        "NO STILL IMAGES: all B-roll must be moving video clips (camera or subject in motion), never static photos.\n"
        "Presenter: use the selected HeyGen avatar and voice (do not substitute a different person).\n",
        f"BACKGROUNDS (change per scene as the script dictates): {background}\n",
        f"VISUAL STYLE: {visual_style}\n",
        f"{SCRIPT_VISUAL_SYNC_RULE}\n",
        f"{script_rule}\n",
        f"SPOKEN SCRIPT (presenter must speak this exactly):\n{spoken_for_prompt}\n",
    ]
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
    system = """You are a senior performance video scriptwriter for Australian Meta video ads.
Fill the production skeleton with concrete scene directions and spoken lines.
Keep all section headers and [timing] blocks exactly as in the draft.
If approved_spoken_script is provided, Avatar Speaks and VO lines MUST use those exact words
(split across sections in story order) — do not write different dialogue.
Each Scene Direction must say what B-roll to show WHILE that beat is spoken (same topic).
On-screen text: short punchy mobile lines matching what is said in that beat.
Headlines in lower third during talking-head — never over the face.
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
        text = str(manual).strip()
        text = re.sub(r"\[\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\]\s*", "", text)
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
