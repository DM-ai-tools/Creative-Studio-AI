"""Parse a client Meta-ads strategy markdown into a CreativeStudio brief."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings
from app.services.ad_angle_library import VALID_ANGLE_IDS, normalize_angle_id

logger = logging.getLogger(__name__)

_OBJECTIVES = {
    "lead_generation",
    "conversions",
    "add_to_cart",
    "traffic",
    "awareness",
}
_FORMATS = {"static", "reel", "video", "carousel"}
_FORMAT_ALIASES = {
    "static": "static",
    "static_image": "static",
    "staticimage": "static",
    "image": "static",
    "still": "static",
    "carousel": "carousel",
    "carousel_card": "carousel",
    "carousel_cards": "carousel",
    "swipe": "carousel",
    "reel": "reel",
    "reels": "reel",
    "video": "video",
    "landscape": "video",
    "portrait": "reel",
}
_PLACEMENTS = {"feed", "reels", "stories", "landscape", "marketplace"}
_USE_CASES = {
    "lifestyle",
    "product",
    "product_person",
    "ugc",
    "testimonial",
    "before_after",
    "unboxing",
    "hero",
    "social_proof",
    "consultation",
    "graphic",
    "hero_product",
    "multi_angle",
    "detail_texture",
    "color_swatch",
    "bs_emotional_using",
}

_FASHION_RETAIL_ANGLES = (
    "offer_urgency",
    "fomo_scarcity",
    "ugc_style",
    "social_proof",
    "pattern_interrupt",
    "curiosity_hook",
)

_OBJECTIVE_ALIASES = {
    "lead": "lead_generation",
    "leads": "lead_generation",
    "lead gen": "lead_generation",
    "lead generation": "lead_generation",
    "enquiry": "lead_generation",
    "appointment": "lead_generation",
    "purchase": "conversions",
    "sales": "conversions",
    "conversion": "conversions",
    "conversions": "conversions",
    "cart": "add_to_cart",
    "traffic": "traffic",
    "awareness": "awareness",
    "reach": "awareness",
}

_GEO_ALIASES = (
    ("melbourne", "Melbourne VIC"),
    ("sydney", "Sydney NSW"),
    ("brisbane", "Brisbane QLD"),
    ("gold coast", "Gold Coast QLD"),
    ("perth", "Perth WA"),
    ("adelaide", "Adelaide SA"),
    ("hobart", "Hobart TAS"),
    ("canberra", "ACT"),
    ("nsw", "NSW"),
    ("victoria", "VIC"),
    ("vic", "VIC"),
    ("qld", "QLD"),
    ("queensland", "QLD"),
)


def _map_objective(raw: str) -> str:
    key = (raw or "").strip().lower().replace("_", " ")
    if key in _OBJECTIVES:
        return key
    for needle, oid in _OBJECTIVE_ALIASES.items():
        if needle in key:
            return oid
    return "lead_generation" if "lead" in key else "conversions"


def _map_geo(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    low = text.lower()
    for needle, value in _GEO_ALIASES:
        if needle in low:
            return value
    return text[:80]


def _normalize_format(raw: str) -> str:
    key = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    mapped = _FORMAT_ALIASES.get(key, key)
    return mapped if mapped in _FORMATS else ""


def _clean_list(values: Any, allowed: set[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        key = str(item or "").strip().lower().replace(" ", "_").replace("-", "_")
        if key == "reels":
            key = "reels"
        if key == "stories":
            key = "stories"
        if key not in allowed or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # Truncated model output — salvage brief fields + complete variant objects.
    salvaged = _salvage_truncated_strategy_json(text)
    if salvaged:
        return salvaged
    raise json.JSONDecodeError("Could not parse strategy JSON", text, 0)


def _salvage_truncated_strategy_json(text: str) -> dict[str, Any] | None:
    """Recover usable brief + variants when the LLM hits max_tokens mid-JSON."""
    raw = (text or "").strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        if start < 0:
            return None
        raw = raw[start:]

    # Pull scalar brief fields even if the variants array is cut off.
    out: dict[str, Any] = {}
    for key in (
        "brand_name",
        "industry",
        "niche",
        "geography",
        "age_range",
        "audience_type",
        "languages",
        "objective_id",
        "cta",
        "offer",
        "product_name",
        "ad_copy_tone",
        "notes",
        "reasoning",
    ):
        m = re.search(
            rf'"{key}"\s*:\s*"((?:\\.|[^"\\])*)"',
            raw,
            flags=re.DOTALL,
        )
        if m:
            try:
                out[key] = json.loads(f'"{m.group(1)}"')
            except json.JSONDecodeError:
                out[key] = m.group(1)

    for key in ("placements", "formats", "hook_frameworks"):
        m = re.search(rf'"{key}"\s*:\s*(\[[^\]]*\])', raw)
        if m:
            try:
                val = json.loads(m.group(1))
                if isinstance(val, list):
                    out[key] = val
            except json.JSONDecodeError:
                pass

    variants: list[dict[str, Any]] = []
    # Match each complete {...} object inside the variants array (best-effort).
    arr_m = re.search(r'"variants"\s*:\s*\[', raw)
    if arr_m:
        chunk = raw[arr_m.end() :]
        depth = 0
        start = -1
        in_str = False
        esc = False
        for i, ch in enumerate(chunk):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    blob = chunk[start : i + 1]
                    try:
                        obj = json.loads(blob)
                        if isinstance(obj, dict):
                            variants.append(obj)
                    except json.JSONDecodeError:
                        pass
                    start = -1
            elif ch == "]" and depth == 0:
                break

    if variants:
        out["variants"] = variants
    if out.get("variants") or out.get("cta") or out.get("product_name") or out.get("niche"):
        logger.warning(
            "Strategy parse salvaged truncated JSON (%s variants)",
            len(out.get("variants") or []),
        )
        return out
    return None


_THEME_ALIASES = {
    "moment": "pain_led",
    "the_moment": "pain_led",
    "emotion": "pain_led",
    "experience": "educational",
    "the_experience": "educational",
    "consultation": "educational",
    "proof": "social_proof",
    "the_proof": "social_proof",
    "review": "testimonial",
    "reviews": "testimonial",
}


def _map_angle(raw: str) -> str:
    direct = normalize_angle_id(raw)
    if direct:
        return direct
    key = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if key in _THEME_ALIASES:
        return _THEME_ALIASES[key]
    for needle, aid in _THEME_ALIASES.items():
        if needle in key:
            return aid
    return ""


def _normalize_parsed_product_focus(raw: str, prompt: str = "") -> str:
    """Map an LLM-returned product_focus string to one of our canonical values.

    Also performs a lightweight heuristic on the visual prompt text so that
    even if the LLM omits the field, obvious graphic / stat cards get
    'product_only' and person-centric concepts get 'with_person'.
    """
    v = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if v in {"product_only", "product_alone", "product_hero", "catalog", "solo"}:
        return "product_only"
    if v in {"product_with_person", "product_and_person", "product_lifestyle", "product_hero_person"}:
        return "product_with_person"
    if v in {"with_person", "with_model", "with_people", "lifestyle_person", "person"}:
        return "with_person"
    # Heuristic fallback from prompt text when LLM left it blank.
    # Covers all industries: jewellery, dental, roofing, HVAC, automotive,
    # landscaping, gardening, turf, trade services, and generic retail.
    p = (prompt or "").lower()
    if v == "" and p:
        # Pure graphic / stat / info-card → product_only (no people needed)
        _graphic_signals = (
            "graphic", "icon", "badge", "stat", "number", "clean background",
            "white background", "minimal", "3 steps", "3-step", "process card",
            "logo", "wordmark", "infographic", "text card", "quote card",
            "testimonial card", "review card", "google review", "star rating",
            "checklist", "comparison", "before/after text", "price card",
            "discount", "offer card", "percentage off", "benefits list",
            "why choose", "our process", "step by step",
        )
        # Person is the main subject — product is secondary or in background
        _person_hero_signals = (
            "couple", "jeweller", "jeweler", "consultation", "boutique",
            "sitting across", "person", "people", "model", "woman", "man",
            "homeowner", "technician", "tradie", "customer", "client",
            # trade / service industries
            "mechanic", "worker", "crew", "team", "staff", "employee",
            "plumber", "electrician", "installer", "operator", "driver",
            "contractor", "roofer", "hvac tech", "landscape crew",
            # dental / health
            "patient", "dentist", "hygienist", "practitioner", "doctor",
            "smile", "smiling", "laughing",
            # lifestyle generic
            "family", "couple", "homeowner sitting", "customer smiling",
            "before and after", "happy customer",
        )
        # Product + body-part or product being used / worn / held close-up
        _product_lifestyle_signals = (
            # jewellery
            "hand", "ring on", "wearing", "wrist", "collarbone", "finger",
            "necklace on", "bracelet on", "held by", "in hand",
            # automotive parts on vehicle
            "installed on", "fitted to", "mounted on", "on the car",
            "on the vehicle", "under the hood", "in the engine bay",
            # turf / landscaping applied to surface
            "turf laid", "grass installed", "lawn installed", "applied to lawn",
            "artificial turf on", "garden with product",
            # tool / equipment being used
            "being used", "in use", "technician using", "worker using",
            "holding the", "applying the", "spraying the",
        )
        if any(s in p for s in _product_lifestyle_signals):
            return "product_with_person"
        if any(s in p for s in _person_hero_signals):
            return "with_person"
        if any(s in p for s in _graphic_signals):
            return "product_only"
    return ""


def _normalize_variant(item: dict[str, Any], fallback_cta: str, fallback_offer: str) -> dict[str, Any]:
    fmt = _normalize_format(str(item.get("format") or "static")) or "static"
    angle = _map_angle(str(item.get("ad_angle") or item.get("theme") or ""))
    use_cases = _clean_list(item.get("use_cases") or [], _USE_CASES) or ["lifestyle"]
    hook = str(item.get("hook") or item.get("headline") or "").strip()
    message = str(item.get("message") or item.get("primary_text") or "").strip()
    prompt = str(item.get("prompt") or item.get("visual_direction") or "").strip()
    creative_type = str(item.get("creative_type") or "photo").strip().lower()
    if creative_type not in {"photo", "graphic", "video"}:
        creative_type = "graphic" if any(k in (prompt + hook).lower() for k in ("graphic", "icon", "badge", "number")) else "photo"
    try:
        c_idx = int(item.get("carousel_index") or 0) or None
        c_tot = int(item.get("carousel_total") or 0) or None
    except (TypeError, ValueError):
        c_idx, c_tot = None, None
    if "cta" in item:
        cta_val = str(item.get("cta") or "").strip()[:80]
    else:
        cta_val = ""
    if not cta_val:
        cta_val = str(fallback_cta or "").strip()[:80]
    return {
        "id": str(item.get("id") or "").strip(),
        "format": fmt,
        "ad_angle": angle,
        "use_cases": use_cases,
        "hook": hook[:240],
        "message": message[:600],
        "image_hook": str(item.get("image_hook") or "").strip()[:80],
        "image_headline": str(item.get("image_headline") or "").strip()[:100],
        "cta": cta_val,
        "offer": str(item.get("offer") or fallback_offer).strip()[:160],
        "prompt": prompt[:4000],
        "reasoning": str(item.get("reasoning") or item.get("theme") or "").strip()[:400],
        "creative_type": creative_type,
        "carousel_index": c_idx,
        "carousel_total": c_tot,
        "carousel_group": str(item.get("carousel_group") or "").strip()[:40] or None,
        "photo_only": bool(item.get("photo_only")),
        "retail_promo": bool(item.get("retail_promo")),
        "aspect_ratio": str(item.get("aspect_ratio") or "").strip()[:16] or None,
        "product_name": str(item.get("product_name") or item.get("product") or "").strip()[:120],
        "post_type": str(item.get("post_type") or "").strip()[:80],
        "design_notes": str(item.get("design_notes") or "").strip()[:1200],
        "product_focus": _normalize_parsed_product_focus(str(item.get("product_focus") or ""), prompt),
    }


_DANGLING_LAST = {
    "your", "our", "my", "at", "an", "a", "the", "of", "for", "to", "and", "or",
    "with", "in", "on", "from", "by", "is", "are", "its",
}
_CARD_SPLIT_RE = re.compile(
    r"(?:Card|Slide|Panel)\s*(\d+)\s*[:.\-–]\s*(.+?)(?=(?:Card|Slide|Panel)\s*\d+\s*[:.\-–]|$)",
    re.I | re.S,
)
_COLLAGE_NOISE_RE = re.compile(
    r"(?is)"
    r"(?:four|4|five|5|three|3)[-\s]?card\s+carousel\s+layout[^.]*\.?|"
    r"no text on images themselves[^.]*\.?|"
    r"captions appear below each card[^.]*\.?|"
    r"each card a distinct editorial photograph[^.]*\.?|"
    r"cards sized for mobile carousel format[^.]*\.?"
)


def _is_incomplete_phrase(text: str) -> bool:
    words = [w for w in (text or "").strip().split() if w]
    if not words:
        return True
    last = re.sub(r"[^a-z']", "", words[-1].lower())
    return last in _DANGLING_LAST


def _prefer_complete_line(candidate: str, fallback: str, max_words: int = 8) -> str:
    cand = (candidate or "").strip()
    fb = (fallback or "").strip()
    if cand and not _is_incomplete_phrase(cand):
        return cand[:120]
    fb_words = fb.split()
    if 1 <= len(fb_words) <= max_words:
        return fb
    words = fb_words[:max_words]
    while words and re.sub(r"[^a-z']", "", words[-1].lower()) in _DANGLING_LAST:
        words.pop()
    return " ".join(words).strip()


def _strip_collage_language(prompt: str) -> str:
    cleaned = _COLLAGE_NOISE_RE.sub(" ", prompt or "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _card_title(scene: str) -> str:
    first = (scene or "").split(".")[0]
    first = re.sub(r"\([^)]*\)", "", first)
    first = re.sub(r"\s+", " ", first).strip(" .;—-")
    words = first.split()
    if 1 <= len(words) <= 8 and not _is_incomplete_phrase(first):
        return first
    return ""


def _extract_card_scenes(text: str) -> list[str]:
    matches = list(_CARD_SPLIT_RE.finditer(text or ""))
    if len(matches) < 2:
        return []
    by_n: dict[int, str] = {}
    for m in matches:
        n = int(m.group(1))
        scene = re.sub(r"\s+", " ", m.group(2)).strip(" .;—-")
        if scene:
            by_n[n] = scene[:800]
    return [by_n[k] for k in sorted(by_n)] if len(by_n) >= 2 else []


_MAX_STRATEGY_VARIANTS = 100

_CREATIVE_SPLIT_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?\*{0,2}\s*CREATIVE\s+(\d+)"
    r"(?:\s*[–—\-:]\s*(.+?))?\s*\*{0,2}\s*$",
)
_CARD_HEADER_RE = re.compile(
    r"(?m)^(?:#{2,4}\s*)?\*{0,2}\s*Card\s+(\d+)\s*(?:[–—\-:].*?)?\*{0,2}\s*$",
    re.I,
)
_CTA_CARD_RE = re.compile(
    r"(?i)\b(?:book\s+your|enquire\s+now|learn\s+more|get\s+a\s+quote|cta\b|"
    r"free\s+desktop\s+assessment|contact\s+us|shop\s+now)\b"
)


def _strip_md_noise(text: str) -> str:
    t = re.sub(r"\*+", "", text or "")
    t = re.sub(r"\s+", " ", t).strip(" .;—-\n\t")
    return t


def _overlay_from_card_body(body: str) -> str:
    """Pull Overlay / Headline text from a card body when present."""
    m = re.search(
        r"(?is)(?:Overlay(?:\s*text)?|Headline)\s*:?\s*(.+?)(?=(?:\n\s*(?:CTA|Card)\b)|$)",
        body or "",
    )
    if not m:
        return ""
    lines = []
    for line in m.group(1).splitlines():
        cleaned = _strip_md_noise(line)
        if cleaned and cleaned.lower() not in {"overlay", "overlay text", "headline"}:
            lines.append(cleaned)
    return " ".join(lines)[:160]


def _scene_from_card_body(body: str) -> str:
    """Visual direction without overlay/CTA blocks."""
    cleaned = re.sub(
        r"(?im)^\s*\*{0,2}\s*(?:Overlay(?:\s*text)?|Headline|Hook|Message|Primary Text|CTA)\s*:?\s*\*{0,2}.*$",
        " ",
        body or "",
    )
    cleaned = re.sub(
        r"(?im)^\s*\*{0,2}\s*(?:Visual|Creative(?:\s+Direction)?|Image Direction)\s*:?\s*\*{0,2}\s*",
        "",
        cleaned,
    )
    cleaned = _strip_md_noise(cleaned)
    return cleaned[:500]


_CREATIVE_FIELD_NAMES = (
    "Hook",
    "Headline",
    "Message",
    "Primary Text",
    "Description",
    "Description (Below Headline)",
    "Body Copy",
    "Creative",
    "Creative Direction",
    "Creative Design Direction",
    "Visual",
    "Visual Direction",
    "Image Direction",
    "On-image Hook",
    "On-image Headline",
    "Image Hook",
    "Image Headline",
    "Design Notes",
    "Overlay",
    "Overlay Text",
    "CTA",
    "CTA Button",
    "Post Type",
    "Product",
    "Benefits",
)


def _extract_loose_creative_field(text: str, names: tuple[str, ...]) -> str:
    """Read labelled creative fields from common MD/DOCX heading styles."""
    if not text:
        return ""
    wanted = "|".join(
        re.escape(name) for name in sorted(names, key=len, reverse=True)
    )
    all_fields = "|".join(
        re.escape(name) for name in sorted(_CREATIVE_FIELD_NAMES, key=len, reverse=True)
    )
    pattern = re.compile(
        rf"(?ims)^\s*(?:#{1,6}\s*)?\*{{0,2}}\s*(?:{wanted})"
        rf"(?:\s*\([^)\n]*\))?\s*:?\s*\*{{0,2}}\s*"
        rf"(?P<value>.*?)(?=^\s*(?:#{1,6}\s*)?\*{{0,2}}\s*(?:{all_fields})"
        rf"(?:\s*\([^)\n]*\))?\s*:?\s*\*{{0,2}}\s*|"
        rf"^\s*(?:#{1,6}\s*)?\*{{0,2}}\s*Card\s+\d+\b|\Z)"
    )
    match = pattern.search(text)
    if not match:
        return ""
    raw_value = re.split(
        r"(?im)\n\s*#{1,6}\s*Card\s+\d+\b",
        match.group("value"),
        maxsplit=1,
    )[0]
    value = _strip_md_noise(raw_value)
    return value[:1200]


def _is_cta_card(body: str, overlay: str) -> bool:
    hay = f"{body}\n{overlay}"
    if re.search(r"(?i)\bCard\s+\d+\s*[–—\-].*\bCTA\b", hay):
        return True
    if re.search(r"(?im)^\s*CTA\s*$", body or ""):
        return True
    # Short card that is mostly a CTA line (Creative 1 Card 6).
    words = _strip_md_noise(body).split()
    if len(words) <= 12 and _CTA_CARD_RE.search(body or ""):
        return True
    if overlay and len(overlay.split()) <= 10 and _CTA_CARD_RE.search(overlay):
        return True
    return False


def _cards_from_arrow_list(section: str) -> list[dict[str, Any]]:
    """Creative 2 style: Visual / lines separated by ↓ ending in CTA."""
    m = re.search(r"(?is)##?\s*\*{0,2}\s*Visual\*{0,2}\s*(.+)$", section)
    block = m.group(1) if m else section
    parts = re.split(r"[↓⬇]|->", block)
    cards: list[dict[str, Any]] = []
    for part in parts:
        scene = _strip_md_noise(part)
        if not scene or len(scene) < 2:
            continue
        if scene.lower() in {"visual", "concept", "headline"}:
            continue
        is_cta = scene.lower() in {"cta", "cta."} or (
            len(scene.split()) <= 8 and _CTA_CARD_RE.search(scene)
        )
        cards.append(
            {
                "scene": "CTA closer" if scene.lower().startswith("cta") else scene[:500],
                "overlay": "" if is_cta or scene.lower().startswith("cta") else scene[:120],
                "is_cta": is_cta or scene.lower().startswith("cta"),
                "body": part[:1200],
            }
        )
    return cards if len(cards) >= 2 else []


def _cards_from_numbered_headers(section: str) -> list[dict[str, Any]]:
    matches = list(_CARD_HEADER_RE.finditer(section or ""))
    if len(matches) < 2:
        matches = list(
            re.finditer(
                r"(?is)(?:^|\n)\s*\*{0,2}\s*Card\s+(\d+)\s*(?:[–—\-:].*?)?\*{0,2}\s*"
                r"(?:\n+)(.+?)(?=(?:\n\s*\*{0,2}\s*Card\s+\d+)|\Z)",
                section or "",
            )
        )
        if len(matches) < 2:
            return []
        by_n: dict[int, dict[str, Any]] = {}
        for m in matches:
            n = int(m.group(1))
            body = m.group(2)
            overlay = _overlay_from_card_body(body)
            scene = _scene_from_card_body(body) or overlay
            by_n[n] = {
                "scene": scene or f"Carousel card {n}",
                "overlay": overlay,
                "is_cta": _is_cta_card(body, overlay),
                "body": body[:1200],
            }
        return [by_n[k] for k in sorted(by_n)]

    by_n = {}
    for i, m in enumerate(matches):
        n = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        body = section[start:end]
        overlay = _overlay_from_card_body(body)
        scene = _scene_from_card_body(body) or overlay
        heading = m.group(0)
        by_n[n] = {
            "scene": scene or f"Carousel card {n}",
            "overlay": overlay,
            "is_cta": _is_cta_card(f"{heading}\n{body}", overlay),
            "body": body[:1200],
        }
    return [by_n[k] for k in sorted(by_n)] if len(by_n) >= 2 else []


_EMBEDDED_IMAGE_REF_RE = re.compile(r"!?\[[^\]]*\]?\[image\d+\]", re.I)
_EMBEDDED_IMAGE_DEF_RE = re.compile(
    r"^\[image\d+\]:\s*<data:image/[^>]+>\s*$",
    re.M | re.I,
)
_CREATIVE_DIRECTION_HDR_RE = re.compile(
    r"(?is)\*\*Creative Direction\s+(\d+)\s*[–—\-]\s*(.+?)\*\*",
)


def strip_embedded_images_for_parse(text: str) -> str:
    """Remove markdown embedded base64 images so LLM excerpts stay usable."""
    t = _EMBEDDED_IMAGE_REF_RE.sub("", text or "")
    t = _EMBEDDED_IMAGE_DEF_RE.sub("", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _extract_md_section(body: str, name: str) -> str:
    m = re.search(
        rf"(?is)\*\*{re.escape(name)}\*\*\s*\n+(.+?)(?=\n\s*\*\*[A-Za-z]|\Z)",
        body or "",
    )
    if not m:
        return ""
    lines: list[str] = []
    for line in m.group(1).splitlines():
        cleaned = _strip_md_noise(line.lstrip("•·-* \t"))
        if cleaned:
            lines.append(cleaned)
    return " ".join(lines)[:500]


def _is_static_image_type(raw: str) -> bool:
    low = (raw or "").lower().replace("/", " ")
    if any(k in low for k in ("gif", "video", "motion", "animation", "reel", "short video")):
        return False
    return "static" in low or ("image" in low and "gif" not in low)


def _is_fashion_retail_doc(text: str, variants: list[dict[str, Any]]) -> bool:
    if any(v.get("retail_promo") or v.get("photo_only") for v in variants):
        return True
    hay = (text or "").lower()
    return any(
        k in hay
        for k in (
            "creative direction",
            "runway",
            "new arrivals",
            "fashion first",
            "editorial fashion",
            "wardrobe",
            "knitwear",
            "boutique premium fashion",
            "denim edit",
        )
    )


def _infer_fashion_use_cases(*, visual: str, title: str, concept: str) -> list[str]:
    hay = f"{visual} {title} {concept}".lower()
    if any(
        k in hay
        for k in (
            "3–4",
            "3-4",
            "multiple",
            "mix of",
            "pieces in one",
            "lineup",
            "side by side",
            "side-by-side",
            "rotation",
            "denim edit",
            "product rotation",
        )
    ):
        return ["multi_angle", "color_swatch", "lifestyle"]
    if any(k in hay for k in ("denim", "jeans", "pants", "trousers", "embellish", "rhinestone")):
        return ["product_person", "detail_texture", "lifestyle"]
    if any(k in hay for k in ("hero model", "full new-arrival look", "full-length", "full length")):
        return ["product_person", "bs_emotional_using", "lifestyle"]
    if any(k in hay for k in ("jackets", "knitwear", "layering", "essentials", "shirts")):
        return ["product_person", "detail_texture", "lifestyle"]
    return ["lifestyle", "product_person"]


def _infer_fashion_aspect_ratio(*, visual: str, title: str) -> str:
    hay = f"{visual} {title}".lower()
    if any(
        k in hay
        for k in (
            "3–4",
            "3-4",
            "multiple pieces",
            "lineup",
            "side by side",
            "denim edit",
            "product rotation",
            "magazine-style layout",
        )
    ):
        return "1:1"
    if any(
        k in hay
        for k in (
            "full-length",
            "full length",
            "walking",
            "hero model",
            "three-quarter",
            "9:16",
            "reels",
            "stories",
        )
    ):
        return "9:16"
    if any(k in hay for k in ("4:5", "portrait feed", "instagram portrait")):
        return "4:5"
    return "1:1"


def _fashion_on_image_headline(primary: str, secondary: str, offer: str) -> tuple[str, str]:
    """Split MD overlays into short burned lines (hook + headline/sub-offer)."""
    hook = (primary or "").strip()[:80]
    headline = ""
    blob = "\n".join(x for x in (secondary, offer) if (x or "").strip())
    lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
    if lines:
        headline = lines[0][:100]
        if len(lines) > 1:
            code_line = next((ln for ln in lines[1:] if "code" in ln.lower()), "")
            if code_line:
                headline = f"{headline} · {code_line}"[:100]
    return hook, headline


def _fashion_retail_promo_scene_prompt(
    *,
    concept: str,
    visual: str,
    title: str,
    aspect_ratio: str,
) -> str:
    """Retail promo ad — models + clothes hero; copy burned in post."""
    parts: list[str] = []
    if concept:
        parts.append(concept)
    if visual:
        parts.append(visual)
    base = ". ".join(parts).strip() or title
    layout = (
        "Premium fashion retail Meta ad — photoreal editorial campaign. "
        "Models wearing the clothes are the hero; sharp product detail on denim, knitwear, or featured garments. "
        "Clean urban street or boutique background, bright natural daylight. "
    )
    if aspect_ratio == "1:1":
        layout += (
            "Square 1:1 feed layout: models side-by-side or grouped lineup when multiple pieces are shown; "
            "lower third kept clean for headline, offer line, promo code pill, and CTA bar. "
        )
    elif aspect_ratio == "9:16":
        layout += (
            "Tall 9:16 portrait: full-length or three-quarter models, vertical composition, "
            "lower third reserved for headline + offer overlay. "
        )
    else:
        layout += f"{aspect_ratio} portrait composition with lower third clear for promo text overlay. "
    layout += (
        "Brand logo composited top-right in post — do not invent a fake wordmark. "
        "Fashion-first, promotion-second aesthetic."
    )
    return f"{base}. {layout}"[:500]


def _fashion_retail_scene_prompt(*, concept: str, visual: str, title: str) -> str:
    """Photo-only fashion ad: model + outfit, no on-image copy."""
    parts: list[str] = []
    if concept:
        parts.append(concept)
    if visual:
        vis = re.sub(
            r"(?i)(minimal text overlay|eofy offer.*?|clean premium typography|"
            r"typography|text overlay|offer displayed|offer positioned|offer featured|"
            r"offer appears|offer introduced)[^.]*\.?",
            "",
            visual,
        )
        vis = re.sub(r"\s{2,}", " ", vis).strip(" .;")
        if vis:
            parts.append(vis)
    base = ". ".join(parts).strip() or title
    return (
        f"{base}. Full-length or three-quarter fashion model wearing the new-arrival outfit — "
        "person and clothes are the hero. Premium realistic boutique or editorial studio background. "
        "Photo only — no text, slogans, badges, or CTA burned into the image."
    )[:500]


def _extract_creative_directions_from_markdown(
    markdown: str,
    *,
    campaign_cta: str,
    campaign_offer: str,
) -> list[dict[str, Any]]:
    """
    Parse **Creative Direction N** blocks (fashion retail briefs).
    Keeps Static Image rows only; skips GIF / video directions.
    """
    text = markdown or ""
    headers = list(_CREATIVE_DIRECTION_HDR_RE.finditer(text))
    if not headers:
        return []

    variants: list[dict[str, Any]] = []
    for hi, hm in enumerate(headers):
        creative_n = int(hm.group(1))
        title = _strip_md_noise(hm.group(2))[:120]
        start = hm.end()
        end = headers[hi + 1].start() if hi + 1 < len(headers) else len(text)
        section = text[start:end]

        creative_type = _extract_md_section(section, "Creative Type")
        if not _is_static_image_type(creative_type):
            continue

        concept = _extract_md_section(section, "Concept")
        visual = _extract_md_section(section, "Visual Direction")
        primary = _extract_md_section(section, "Primary Text Overlay")
        secondary = _extract_md_section(section, "Secondary Text Overlay")
        messaging = _extract_md_section(section, "Messaging Angle")
        cta = _extract_md_section(section, "CTA") or (campaign_cta or "").strip()[:80]
        offer_line = secondary or campaign_offer
        aspect_ratio = _infer_fashion_aspect_ratio(visual=visual, title=title)
        use_cases = _infer_fashion_use_cases(visual=visual, title=title, concept=concept)
        img_hook, img_headline = _fashion_on_image_headline(primary, secondary, campaign_offer)
        prompt = _fashion_retail_promo_scene_prompt(
            concept=concept,
            visual=visual,
            title=title,
            aspect_ratio=aspect_ratio,
        )
        variants.append(
            {
                "id": f"D{creative_n}",
                "format": "static",
                "ad_angle": _FASHION_RETAIL_ANGLES[(creative_n - 1) % len(_FASHION_RETAIL_ANGLES)],
                "use_cases": use_cases,
                "hook": primary or title,
                "message": messaging or concept or title,
                "image_hook": img_hook,
                "image_headline": img_headline,
                "cta": cta,
                "offer": offer_line,
                "prompt": prompt,
                "reasoning": (
                    f"Creative Direction {creative_n}: {title} · retail promo · {aspect_ratio} · "
                    f"use_cases={','.join(use_cases)}"
                ),
                "creative_type": "photo",
                "carousel_index": None,
                "carousel_total": None,
                "carousel_group": None,
                "retail_promo": True,
                "photo_only": False,
                "aspect_ratio": aspect_ratio,
            }
        )
    return variants


def _prefer_creative_directions(
    markdown: str,
    llm_variants: list[dict[str, Any]],
    *,
    campaign_cta: str,
    campaign_offer: str,
) -> list[dict[str, Any]]:
    structured = _extract_creative_directions_from_markdown(
        markdown,
        campaign_cta=campaign_cta,
        campaign_offer=campaign_offer,
    )
    if len(structured) >= 1:
        logger.info(
            "Strategy MD: using Creative Direction static photos (%s) over LLM variants (%s)",
            len(structured),
            len(llm_variants),
        )
        return structured
    return llm_variants


_ORGANIC_POST_SPLIT_RE = re.compile(
    r"(?is)\*{0,2}\s*ORGANIC\s+POST\s*\\?#\s*(\d+)\s*\*{0,2}",
)
_ORGANIC_FIELD_LABELS = (
    "POST TYPE",
    "PRODUCT",
    "HEADLINE",
    "VISUAL",
    "Left Side",
    "Right Side",
    "BENEFITS SECTION",
    "SUPPORTING TEXT",
    "TEXT",
    "CALLOUTS",
    "Background",
    "TEXT BLOCK",
    "Supporting icons",
    "OPTIONS",
    "BOTTOM SECTION",
    "DESIGN NOTES",
)


def _clean_md_block(text: str) -> str:
    lines: list[str] = []
    for line in (text or "").splitlines():
        cleaned = re.sub(r"\*+", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


def _extract_between_labels(section: str, start_label: str, stop_labels: list[str]) -> str:
    start_re = re.compile(
        rf"(?is)\*{{0,2}}\s*{re.escape(start_label)}\s*:?\s*\*{{0,2}}\s*\n",
    )
    m = start_re.search(section)
    if not m:
        return ""
    rest = section[m.end() :]
    earliest = len(rest)
    for stop in stop_labels:
        if stop == start_label:
            continue
        stop_re = re.compile(rf"(?is)\n\*{{1,2}}\s*{re.escape(stop)}\s*:?\s*\*{{0,2}}")
        sm = stop_re.search(rest)
        if sm:
            earliest = min(earliest, sm.start())
    dash = rest.find("\n---")
    if dash >= 0:
        earliest = min(earliest, dash)
    tail = re.search(r"(?is)\n\*{1,2}\s*Organic posting\s*\*{0,2}", rest)
    if tail:
        earliest = min(earliest, tail.start())
    return _clean_md_block(rest[:earliest])


def _map_organic_post_angle(post_type: str) -> str:
    low = (post_type or "").lower()
    if "problem" in low or "solution" in low:
        return "problem_agitate_solve"
    if "trust" in low or "community" in low:
        return "social_proof"
    if "authority" in low or "founder" in low:
        return "founder_led"
    if "awareness" in low or "curiosity" in low or "engagement" in low:
        return "curiosity_hook"
    if "lifestyle" in low:
        return "ugc_style"
    if "offer" in low or "urgency" in low:
        return "offer_urgency"
    return "educational"


def _extract_organic_posts_from_markdown(markdown: str) -> list[dict[str, Any]]:
    """
    Deterministic parse for docs like:
      ORGANIC POST #1 … ORGANIC POST #10
    Each post becomes one static variant with full MD visual/design instructions preserved.
    """
    text = (markdown or "").split("**Organic posting**")[0]
    headers = list(_ORGANIC_POST_SPLIT_RE.finditer(text))
    if len(headers) < 2:
        return []

    variants: list[dict[str, Any]] = []
    stops = list(_ORGANIC_FIELD_LABELS)
    for hi, hm in enumerate(headers):
        post_n = int(hm.group(1))
        start = hm.end()
        end = headers[hi + 1].start() if hi + 1 < len(headers) else len(text)
        section = text[start:end]

        post_type = _extract_between_labels(section, "POST TYPE", stops)
        product = _extract_between_labels(section, "PRODUCT", stops)
        headline = _extract_between_labels(section, "HEADLINE", stops)
        visual = _extract_between_labels(section, "VISUAL", stops)
        benefits = _extract_between_labels(section, "BENEFITS SECTION", stops)
        supporting = _extract_between_labels(section, "SUPPORTING TEXT", stops) or _extract_between_labels(
            section, "TEXT", stops
        )
        callouts = _extract_between_labels(section, "CALLOUTS", stops)
        background = _extract_between_labels(section, "Background", stops)
        text_block = _extract_between_labels(section, "TEXT BLOCK", stops)
        icons = _extract_between_labels(section, "Supporting icons", stops)
        options = _extract_between_labels(section, "OPTIONS", stops)
        bottom = _extract_between_labels(section, "BOTTOM SECTION", stops)
        design_notes = _extract_between_labels(section, "DESIGN NOTES", stops)

        prompt_parts: list[str] = []
        if visual:
            prompt_parts.append(f"VISUAL:\n{visual}")
        if background:
            prompt_parts.append(f"BACKGROUND:\n{background}")
        for label, block in (
            ("BENEFITS", benefits),
            ("SUPPORTING", supporting),
            ("CALLOUTS", callouts),
            ("TEXT", text_block),
            ("ICONS", icons),
            ("OPTIONS", options),
        ):
            if block:
                prompt_parts.append(f"{label}:\n{block}")
        if bottom:
            prompt_parts.append(f"BOTTOM SECTION:\n{bottom}")
        if design_notes:
            prompt_parts.append(f"DESIGN NOTES:\n{design_notes}")
        prompt = "\n\n".join(prompt_parts).strip()
        if not prompt and headline:
            prompt = headline

        angle = _map_organic_post_angle(post_type)
        graphic = any(
            k in (post_type + visual + design_notes).lower()
            for k in ("graphic", "illustration", "icon", "flat-lay", "designed")
        )
        variants.append(
            {
                "id": f"OP{post_n}",
                "format": "static",
                "ad_angle": angle,
                "use_cases": ["hero_product", "graphic"] if graphic else ["hero_product", "lifestyle"],
                "hook": headline[:240],
                "message": (bottom or supporting or headline)[:600],
                "image_hook": headline[:80],
                "image_headline": product[:100] if product else headline[:80],
                "cta": "",
                "offer": "",
                "prompt": prompt[:4000],
                "reasoning": f"Organic post #{post_n}: {post_type or 'static'} — {product or headline}",
                "creative_type": "graphic" if graphic else "photo",
                "product_name": product[:120],
                "post_type": post_type[:80],
                "design_notes": design_notes[:1200],
            }
        )
    return variants


_EDM_SECTION_RE = re.compile(
    r"(?im)^\*\*(?P<title>.+?)\s+EDM\s+(?P<num>\d+)\s*/\s*(?P<total>\d+)\*\*\s*$"
)


def _extract_md_table_field(section: str, field: str) -> str:
    """Read a value from markdown table rows like | **CTA button:** | SHOP NOW |."""
    patterns = (
        rf"(?im)\|\s*\*\*{re.escape(field)}:?\*\*\s*\|\s*(?P<val>[^|\n]+?)\s*\|",
        rf"(?im)\*\*{re.escape(field)}:?\*\*\s*\|\s*(?P<val>[^|\n]+?)\s*\|",
    )
    for pat in patterns:
        m = re.search(pat, section or "")
        if not m:
            continue
        val = _clean_md_block(m.group("val"))
        if val and not val.lower().startswith("[insert"):
            return val[:120]
    inline = re.search(rf"(?i)\b{re.escape(field)}\s*:?\s*(?P<val>[^\n|]+)", section or "")
    if inline:
        val = _clean_md_block(inline.group("val"))
        if val and not val.lower().startswith("[insert"):
            return val[:120]
    return ""


def _map_edm_angle(purpose: str, banner: str) -> str:
    hay = f"{purpose} {banner}".lower()
    if any(k in hay for k in ("trust", "authority", "thousands", "rated")):
        return "social_proof"
    if any(k in hay for k in ("replenish", "restock", "running low", "stock")):
        return "offer_urgency"
    if any(k in hay for k in ("spotlight", "hero product", "back in stock")):
        return "product_hero"
    if any(k in hay for k in ("industry", "hospitality", "school", "medical", "office")):
        return "educational"
    return "social_proof"


def _extract_edms_from_markdown(markdown: str) -> list[dict[str, Any]]:
    """
    Deterministic parse for client EDM calendars, e.g. Bulk Buys August 2026 EDM 1/12 … 12/12.
    Each EDM becomes one static variant with its own CTA button from the MD table.
    """
    text = markdown or ""
    headers = list(_EDM_SECTION_RE.finditer(text))
    if len(headers) < 2:
        return []

    variants: list[dict[str, Any]] = []
    for hi, hm in enumerate(headers):
        edm_n = int(hm.group("num"))
        edm_total = int(hm.group("total"))
        start = hm.end()
        end = headers[hi + 1].start() if hi + 1 < len(headers) else len(text)
        section = text[start:end]

        banner = _extract_md_table_field(section, "Banner text")
        subject = _extract_md_table_field(section, "Subject line")
        preview = _extract_md_table_field(section, "Preview line")
        purpose = _extract_md_table_field(section, "Purpose")
        body = _extract_md_table_field(section, "Body copy")
        cta = _extract_md_table_field(section, "CTA button") or _extract_md_table_field(section, "CTA")
        if not cta:
            body_cta = re.search(r"(?i)\bCTA:\s*(?P<val>[^\n\[]+)", section or "")
            if body_cta:
                cta = _clean_md_block(body_cta.group("val"))[:80]

        hook = banner or subject or preview
        message = purpose or preview or subject or body[:220]
        image_hook = banner or subject or preview
        image_headline = preview or subject or banner

        prompt_parts: list[str] = []
        if purpose:
            prompt_parts.append(f"PURPOSE: {purpose}")
        if banner:
            prompt_parts.append(f"BANNER: {banner}")
        if body:
            prompt_parts.append(f"BODY: {body[:800]}")
        if cta:
            prompt_parts.append(f"CTA BUTTON (burn on image): {cta}")
        prompt = "\n\n".join(prompt_parts).strip() or hook

        variants.append(
            {
                "id": f"EDM{edm_n}",
                "format": "static",
                "ad_angle": _map_edm_angle(purpose, banner),
                "use_cases": ["hero_product", "lifestyle"],
                "hook": hook[:240],
                "message": message[:600],
                "image_hook": (image_hook or hook)[:80],
                "image_headline": (image_headline or hook)[:100],
                "cta": cta[:80],
                "offer": "",
                "prompt": prompt[:4000],
                "reasoning": f"EDM {edm_n}/{edm_total}: {purpose[:140] or subject[:140] or banner[:140]}",
            }
        )
    return variants


def _strategy_parse_model() -> str:
    return (
        settings.OPENROUTER_MODEL_STRATEGY_PARSE
        or settings.OPENROUTER_MODEL_VISION
        or settings.OPENROUTER_MODEL_CLAUDE_SCRIPT
        or settings.OPENROUTER_MODEL_CLAUDE
    )


async def _llm_parse_brief_metadata(text: str, *, filename: str = "") -> dict[str, Any]:
    """Brief-level fields only — variants come from deterministic MD structure."""
    from app.services.image_prompt_service import _get_openrouter_client

    client = _get_openrouter_client()
    excerpt = text[:20000]
    system = (
        "Extract campaign brief metadata from a client strategy document. "
        "Return ONLY JSON — no variants array. Do not invent facts. "
        'Schema: {"brand_name":"","industry":"","niche":"","geography":"","age_range":"",'
        '"audience_type":"","languages":"English","objective_id":"awareness",'
        '"cta":"","offer":"","product_name":"","ad_copy_tone":"",'
        '"placements":[],"formats":["static"],"hook_frameworks":[],"notes":"","reasoning":""}'
    )
    response = client.chat.completions.create(
        model=_strategy_parse_model(),
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Filename: {filename or 'strategy.md'}\n\nStrategy document:\n{excerpt}",
            },
        ],
        max_tokens=4000,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    data = _extract_json(raw)
    if not isinstance(data, dict):
        return {}
    data["variants"] = []
    return data


def _extract_creatives_from_markdown(markdown: str) -> list[dict[str, Any]]:
    """
    Deterministic parse for docs like:
      # CREATIVE 1 – TITLE
      Card 1 ... Card 6 (CTA)
      # CREATIVE 2 ...
    Each CREATIVE is its own Meta carousel. CTA only on that creative's last card.
    """
    text = markdown or ""
    headers = list(_CREATIVE_SPLIT_RE.finditer(text))
    if not headers:
        return []

    variants: list[dict[str, Any]] = []
    for hi, hm in enumerate(headers):
        creative_n = int(hm.group(1))
        title = _strip_md_noise(hm.group(2) or "")[:120]
        start = hm.end()
        end = headers[hi + 1].start() if hi + 1 < len(headers) else len(text)
        section = text[start:end]
        if not title:
            first_line = next(
                (
                    _strip_md_noise(line)
                    for line in section.splitlines()
                    if _strip_md_noise(line)
                ),
                "",
            )
            title = first_line[:120] or f"Creative {creative_n}"

        creative_hook = _extract_loose_creative_field(section, ("Hook",))
        creative_headline = _extract_loose_creative_field(section, ("Headline",))
        creative_message = _extract_loose_creative_field(
            section, ("Message", "Primary Text", "Description", "Description (Below Headline)", "Body Copy")
        )
        creative_visual = _extract_loose_creative_field(
            section,
            (
                "Creative",
                "Creative Direction",
                "Creative Design Direction",
                "Visual",
                "Visual Direction",
                "Image Direction",
            ),
        )
        creative_design = _extract_loose_creative_field(section, ("Design Notes",))
        headline = creative_headline or title

        cards = _cards_from_numbered_headers(section)
        if len(cards) < 2:
            cards = _cards_from_arrow_list(section)
        if len(cards) < 2:
            # Standalone static creatives often have no Card/Slide blocks.
            # In client files like "Headline / Description (Below Headline)",
            # Headline is the primary on-image line. Description is supporting copy.
            explicit_image_hook = _extract_loose_creative_field(
                section, ("On-image Hook", "Image Hook")
            )
            explicit_image_headline = _extract_loose_creative_field(
                section, ("On-image Headline", "Image Headline")
            )
            variants.append(
                {
                    "id": f"C{creative_n}",
                    "format": "static",
                    "ad_angle": "",
                    "use_cases": ["lifestyle"],
                    "hook": creative_hook,
                    "message": creative_message,
                    "image_hook": explicit_image_hook or creative_headline,
                    # In this document format, Description (Below Headline)
                    # is the supporting on-image headline line.
                    "image_headline": explicit_image_headline or creative_message,
                    "cta": _extract_loose_creative_field(section, ("CTA", "CTA Button")),
                    "offer": "",
                    "prompt": "\n\n".join(
                        part for part in (creative_visual, creative_design) if part
                    )[:4000],
                    "reasoning": f"Creative {creative_n}: {title}",
                    "creative_type": "photo",
                    "carousel_index": None,
                    "carousel_total": None,
                    "carousel_group": None,
                    "design_notes": creative_design[:1200],
                    "retail_promo": False,
                    "photo_only": False,
                }
            )
            continue

        total = min(len(cards), 10)
        # Prefer explicit CTA-marked card; else last card is the closer.
        cta_idxs = [i for i, c in enumerate(cards[:total]) if c.get("is_cta")]
        closer_i = cta_idxs[-1] if cta_idxs else total - 1

        for i, card in enumerate(cards[:total]):
            overlay = str(card.get("overlay") or "").strip()
            scene = str(card.get("scene") or "").strip()
            card_body = str(card.get("body") or "")
            card_hook = _extract_loose_creative_field(card_body, ("Hook",))
            card_headline = _extract_loose_creative_field(card_body, ("Headline",))
            card_message = _extract_loose_creative_field(
                card_body,
                ("Message", "Primary Text", "Description", "Description (Below Headline)", "Body Copy"),
            )
            card_visual = _extract_loose_creative_field(
                card_body,
                ("Creative", "Creative Direction", "Visual", "Visual Direction", "Image Direction"),
            )
            # Do not put a headline into the hook field. If the document has no
            # hook, the downstream LLM may create a catchy one from the source.
            exact_hook = card_hook or creative_hook or ""
            exact_headline = card_headline or creative_headline or headline or title
            exact_message = card_message or creative_message or exact_headline
            image_hook = _extract_loose_creative_field(
                card_body, ("On-image Hook", "Image Hook")
            )
            image_headline = _extract_loose_creative_field(
                card_body, ("On-image Headline", "Image Headline")
            )
            is_last = i == closer_i or i == total - 1
            # If an earlier card was marked CTA but there are cards after, only the
            # final CTA-marked (or absolute last) card keeps the button.
            if cta_idxs:
                is_last = i == closer_i
            variants.append(
                {
                    "id": f"C{creative_n}-{i + 1}",
                    "format": "carousel",
                    "ad_angle": "",
                    "use_cases": ["lifestyle"],
                    "hook": exact_hook,
                    "message": exact_message if i == 0 else (card_message or scene[:120]),
                    "image_hook": image_hook or overlay or exact_headline,
                    "image_headline": image_headline or card_message or creative_message,
                    "cta": "",  # filled after we know campaign CTA
                    "offer": "",
                    "prompt": "\n\n".join(
                        part for part in (
                            card_visual or scene or creative_visual or overlay or title,
                            creative_design,
                        ) if part
                    )[:4000],
                    "reasoning": f"Creative {creative_n}: {title} · card {i + 1}/{total}",
                    "creative_type": "photo",
                    "carousel_index": i + 1,
                    "carousel_total": total,
                    "carousel_group": f"creative-{creative_n}",
                    "design_notes": creative_design[:1200],
                    "_is_closer": is_last,
                }
            )
    return variants


def _prefer_structured_creatives(
    markdown: str,
    llm_variants: list[dict[str, Any]],
    campaign_cta: str,
) -> list[dict[str, Any]]:
    """Prefer deterministic CREATIVE/Card structure over LLM guesses when present."""
    structured = _extract_creatives_from_markdown(markdown)
    if len(structured) < 2:
        return llm_variants
    cta = (campaign_cta or "Learn More").strip()[:80]
    out: list[dict[str, Any]] = []
    for v in structured[:_MAX_STRATEGY_VARIANTS]:
        closer = bool(v.pop("_is_closer", False))
        if (v.get("format") or "") == "carousel":
            # Carousel CTA appears only on the final card.
            v["cta"] = cta if closer else ""
        # Standalone static creative already carries its own document CTA.
        out.append(v)
    logger.info(
        "Strategy MD: using structured creatives (%s cards across groups) over LLM variants (%s)",
        len(out),
        len(llm_variants),
    )
    return out


def _explode_carousel_variants(
    variants: list[dict[str, Any]],
    fallback_cta: str,
) -> list[dict[str, Any]]:
    """One Meta carousel row → one variant per swipe card (CTA only on the last card)."""
    out: list[dict[str, Any]] = []
    for v in variants:
        if (v.get("format") or "") != "carousel":
            out.append(v)
            continue
        try:
            already = int(v.get("carousel_total") or 0) >= 2 and int(v.get("carousel_index") or 0) >= 1
        except (TypeError, ValueError):
            already = False
        if already:
            out.append(v)
            continue
        hay = " ".join(
            str(v.get(k) or "") for k in ("prompt", "reasoning", "hook", "message")
        )
        cards = _extract_card_scenes(hay)
        if len(cards) < 2:
            v["carousel_index"] = 1
            v["carousel_total"] = 1
            out.append(v)
            continue
        n = min(len(cards), 8)
        parent_id = str(v.get("id") or "C").strip() or "C"
        for i, scene in enumerate(cards[:n]):
            card = dict(v)
            card["id"] = f"{parent_id}-{i + 1}"
            card["prompt"] = _strip_collage_language(scene) or scene
            card["carousel_index"] = i + 1
            card["carousel_total"] = n
            card["reasoning"] = (
                f"{v.get('reasoning') or parent_id} · Carousel card {i + 1}/{n}"
            )[:400]
            title = _card_title(scene)
            card["image_hook"] = title or _prefer_complete_line(
                str(v.get("image_hook") or ""), str(v.get("hook") or ""), 8
            )
            card["image_headline"] = _prefer_complete_line(
                str(v.get("image_headline") or ""), "", 8
            )
            if _is_incomplete_phrase(card["image_headline"]) or (
                card["image_headline"]
                and card["image_hook"]
                and card["image_headline"].lower() in card["image_hook"].lower()
            ):
                card["image_headline"] = ""
            card["cta"] = (fallback_cta or str(v.get("cta") or "")).strip() if i == n - 1 else ""
            out.append(card)
    for v in out:
        if (v.get("format") or "") != "carousel":
            continue
        try:
            idx = int(v.get("carousel_index") or 0)
            tot = int(v.get("carousel_total") or 0)
        except (TypeError, ValueError):
            continue
        if tot >= 2 and idx and idx < tot:
            v["cta"] = ""
        elif tot >= 2 and idx >= tot and not str(v.get("cta") or "").strip():
            v["cta"] = fallback_cta
    return out


async def _expand_variant_image_prompts(
    brief: dict[str, Any],
    variants: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn each MD visual-direction note into a full image-generation prompt."""
    if not variants:
        return variants
    try:
        from app.services.image_prompt_service import _get_openrouter_client

        client = _get_openrouter_client()
        payload = []
        for i, v in enumerate(variants):
            total = int(v.get("carousel_total") or 0) or 0
            idx = int(v.get("carousel_index") or 0) or 0
            is_last = (v.get("format") or "") != "carousel" or not total or idx >= total
            payload.append(
                {
                    "id": v.get("id") or f"V{i + 1}",
                    "index": i,
                    "format": v.get("format") or "static",
                    "carousel_index": idx or None,
                    "carousel_total": total or None,
                    "is_last_carousel_card": is_last,
                    "scene": (v.get("prompt") or "").strip(),
                    "hook": (v.get("hook") or "").strip(),
                    "message": (v.get("message") or "").strip(),
                    "cta": ((v.get("cta") or brief.get("cta") or "").strip() if is_last else ""),
                    "creative_type": v.get("creative_type") or "photo",
                    "ad_angle": v.get("ad_angle") or "",
                }
            )
        industry = brief.get("industry") or ""
        niche = brief.get("niche") or ""
        system = (
            "You are a world-class advertising image-prompt engineer. "
            "For EACH variant, expand the strategy SCENE into one production prompt "
            "for GPT Image / Flux / Midjourney (120–260 words, ONE paragraph). "
            "The strategy scene is mandatory source of truth — do not swap the category "
            f"(if the brief is {industry or 'this niche'} / {niche or 'this product'}, keep that; "
            "never turn jewellery into furniture or an unrelated industry). "
            "Include: subject, pose/action, environment, lighting, camera/lens, colour, mood, "
            "4K photorealistic quality. Faces sharp and fully visible when people appear. "
            "image_hook and image_headline MUST be complete phrases a stranger can read. "
            "Never truncate mid-thought (ban fragments like 'What happens at your'). "
            "If the source hook is already 8 words or fewer, copy it verbatim as image_hook. "
            "Never split one sentence across image_hook + image_headline. "
            "Carousel cards: ONE square 1:1 photograph for THIS card only — never a 4-panel "
            "collage, never 'four-card layout', never 'no text on images'. "
            "Only the LAST carousel card (is_last_carousel_card=true) gets a CTA pill button "
            "with the given CTA text. Earlier cards: no CTA button on the image. "
            "Static variants: burn SHORT on-image text: image_hook (max 8 words) and "
            "image_headline (max 8 words) plus a CTA button using the given CTA. "
            "Describe placement, type weight, and colour of that text. "
            "If industry/niche is jewellery, jeweller, rings, diamonds, or engagement: "
            "on-image type MUST be metallic champagne-gold (#D4AF37 to burnished bronze). "
            "Headline: elegant serif in Title Case or sentence case — NEVER ALL CAPS. "
            "Supporting line: thin tracked sans-serif sentence case. "
            "Romantic/engagement line: flowing gold script calligraphy (natural casing). "
            f"BRAND NAME LOCK: the only store name allowed on-image is "
            f"\"{brief.get('brand_name') or 'the Brand Kit name'}\" letter-for-letter. "
            "Never invent Lusso, Shop Dimad, She Diamond, or treat 'Shop Diamonds' as the brand. "
            "No cheap white Impact or generic black sans as hero type. "
            "PRODUCT HERO: name the specific jewel and zoom it as the main subject "
            "(large in frame, macro/tight close-up). People and scene may stay as supporting "
            "background — do not delete them, but the product is what the eye hits first. "
            "Do not put the full Facebook primary-text essay on the photo. "
            "Graphic variants: describe a clean designed graphic, not a lifestyle photo. "
            "Each variant must be a different scene. "
            'Return ONLY JSON: {"prompts":[{"id":"","prompt":"","image_hook":"","image_headline":""}]}'
        )
        user = (
            f"Brand: {brief.get('brand_name') or ''}\n"
            f"Industry: {industry}\nNiche: {niche}\n"
            f"Location: {brief.get('geography') or ''}\n"
            f"Audience: {brief.get('audience_type') or ''} {brief.get('age_range') or ''}\n"
            f"Product: {brief.get('product_name') or ''}\n"
            f"Offer: {brief.get('offer') or ''}\n"
            f"Tone: {brief.get('ad_copy_tone') or 'premium editorial'}\n"
            f"Default CTA: {brief.get('cta') or ''}\n\n"
            f"VARIANTS (scene = strategy visual direction):\n{json.dumps(payload, ensure_ascii=False)}"
        )
        response = client.chat.completions.create(
            model=_strategy_parse_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=5000,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        data = _extract_json(raw)
        expanded = data.get("prompts") if isinstance(data.get("prompts"), list) else []
        by_id: dict[str, dict[str, Any]] = {}
        for item in expanded:
            if isinstance(item, dict) and item.get("id"):
                by_id[str(item["id"])] = item
        for i, v in enumerate(variants):
            hit = by_id.get(str(v.get("id") or ""))
            if not hit and i < len(expanded) and isinstance(expanded[i], dict):
                hit = expanded[i]
            if not hit:
                continue
            long_prompt = str(hit.get("prompt") or "").strip()
            if long_prompt:
                v["prompt"] = _strip_collage_language(long_prompt)[:4000] or long_prompt[:4000]
            hook_short = _prefer_complete_line(
                str(hit.get("image_hook") or ""),
                str(v.get("image_hook") or v.get("hook") or ""),
                8,
            )
            head_short = _prefer_complete_line(
                str(hit.get("image_headline") or ""),
                str(v.get("image_headline") or ""),
                8,
            )
            if hook_short:
                v["image_hook"] = hook_short[:80]
            if head_short and not _is_incomplete_phrase(head_short):
                v["image_headline"] = head_short[:100]
            elif _is_incomplete_phrase(str(v.get("image_headline") or "")):
                v["image_headline"] = ""
        from app.services.icp_image_plan_service import enforce_niche_product_focus_in_prompt

        for v in variants:
            v["prompt"] = _strip_collage_language(
                enforce_niche_product_focus_in_prompt(
                    str(v.get("prompt") or ""),
                    niche=str(brief.get("niche") or ""),
                    industry=str(brief.get("industry") or ""),
                    brand_name=str(brief.get("brand_name") or ""),
                )
            )
            v["image_hook"] = _prefer_complete_line(
                str(v.get("image_hook") or ""), str(v.get("hook") or ""), 8
            )
            if _is_incomplete_phrase(str(v.get("image_headline") or "")):
                v["image_headline"] = ""
    except Exception:
        logger.exception("Strategy image-prompt expand failed; keeping short scene notes")
    return variants


async def parse_strategy_markdown(markdown: str, *, filename: str = "") -> dict[str, Any]:
    text = strip_embedded_images_for_parse((markdown or "").strip())
    if len(text) < 40:
        raise ValueError("Strategy file is empty or too short")
    excerpt = text[:24000]

    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not configured")

    organic_raw = _extract_organic_posts_from_markdown(text)
    edm_raw = _extract_edms_from_markdown(text)
    parse_model = _strategy_parse_model()

    from app.services.image_prompt_service import _get_openrouter_client

    client = _get_openrouter_client()
    angle_ids = ", ".join(sorted(VALID_ANGLE_IDS))
    system = (
        "You extract a Meta ads brief from a client strategy document. "
        "Return ONLY JSON. Do not invent facts that are not in the document. "
        f"Map psychological themes onto these ad_angle ids: {angle_ids}. "
        "objective_id must be one of: lead_generation, conversions, add_to_cart, traffic, awareness. "
        "formats must use: static, reel, video, carousel. "
        "Include EVERY format that appears in the document. "
        "If the table has both Carousel and Static Image rows, formats MUST be "
        '["static","carousel"] — never collapse to a single format when both exist. '
        "Each variant.format must match that row's Type column "
        "(Carousel → carousel, Static Image → static). "
        "placements must use: feed, reels, stories, landscape, marketplace. "
        "Each static row becomes one variant. "
        "IMPORTANT — ORGANIC POST #1, #2, … #N: emit ONE variant PER numbered organic post — never merge or summarize. "
        "If the document lists 10 organic posts, variants MUST contain exactly 10 entries. "
        "IMPORTANT — multiple CREATIVES in one document = multiple SEPARATE carousels. "
        "CREATIVE 1 Card 1..6 is carousel A; CREATIVE 2 Card 1..6 is carousel B — do NOT merge them. "
        "Each Carousel creative becomes ONE variant PER CARD (Card 1, Card 2, …). "
        "If the doc says 4 creatives × 6 cards, emit ~24 carousel variants — never one collage. "
        "carousel_index is 1-based WITHIN that creative; carousel_total is THAT creative's card count. "
        "cta is blank on every CAROUSEL card except the LAST card of EACH creative "
        "(e.g. Creative 1 Card 6 AND Creative 2 Card 6 both get the CTA). "
        "For STATIC image variants, EVERY variant MUST include its own cta from the document "
        "(CTA button / CTA row / banner CTA line) — static ads always burn a CTA pill on the image. "
        "variant prompt = copy the document's visual direction / concept verbatim and SHORT "
        "(≤ 160 characters — do not expand into a full image prompt yet). "
        "hook = short on-ad line from the doc (≤ 120 chars); "
        "message = primary text / body copy from the doc (≤ 220 chars). "
        "product_focus: read EACH variant's visual concept description and assign one of these values — "
        "every variant must get its own independent value, do NOT copy the first variant's value to all: "
        "  'product_only'        — product / graphic / text card isolated, NO people at all. "
        "    Examples (any industry): stat card, before/after text card, Google-review quote card, "
        "    product catalog shot on white, HVAC unit on white background, turf roll on grass, "
        "    roof shingle close-up, dental whitening kit on counter, auto part on white. "
        "  'product_with_person' — product IS the clear hero (occupies most of frame) AND a real person is also present. "
        "    Examples: ring on a hand, person wearing necklace, technician holding HVAC part next to unit, "
        "    mechanic's hands on auto parts, dentist showing whitening tray to camera, "
        "    landscaper laying turf (turf is the hero), roofer on roof showing shingle. "
        "  'with_person'         — person / human is the PRIMARY subject; product is visible but background / secondary. "
        "    Examples: homeowner smiling in renovated space, couple at jewellery consultation, "
        "    dentist or patient (face-focused), happy customer holding result, "
        "    tradie team on job site, before/after lifestyle photo of a person. "
        "  ''                    — truly cannot determine (leave blank — rare, only if no visual description at all). "
        "Keep every string compact — large strategy files must still fit in one JSON response.\n"
        "Schema: {\n"
        '  "brand_name": "", "industry": "", "niche": "", "geography": "",\n'
        '  "age_range": "", "audience_type": "", "languages": "English",\n'
        '  "objective_id": "lead_generation", "cta": "", "offer": "",\n'
        '  "product_name": "", "ad_copy_tone": "", "placements": [],\n'
        '  "formats": [], "hook_frameworks": [], "notes": "", "reasoning": "",\n'
        '  "variants": [{"id": "T1", "format": "static", "ad_angle": "pain_led",\n'
        '    "use_cases": ["lifestyle"], "hook": "", "message": "", "image_hook": "",\n'
        '    "image_headline": "", "cta": "", "offer": "", "prompt": "",\n'
        '    "reasoning": "", "creative_type": "photo", "carousel_index": null,\n'
        '    "carousel_total": null, "product_focus": ""}]\n'
        "}"
    )

    if len(edm_raw) >= 2:
        logger.info(
            "Strategy MD: detected %s EDM sections — using deterministic parse + Gemini brief metadata",
            len(edm_raw),
        )
        try:
            data = await _llm_parse_brief_metadata(text, filename=filename)
        except Exception:
            logger.exception("Strategy brief metadata LLM failed; using heuristics")
            data = {}
        if not isinstance(data, dict):
            data = {}
        if not str(data.get("brand_name") or "").strip():
            m = re.search(r"(?im)^\*\*(Bulk Buys|.+?)\s+EDM", text)
            if m:
                data["brand_name"] = _clean_md_block(m.group(1))[:120]
        if not str(data.get("industry") or "").strip():
            data["industry"] = "Retail"
        if not str(data.get("niche") or "").strip():
            data["niche"] = "Workplace supplies"
        if not str(data.get("objective_id") or "").strip():
            data["objective_id"] = "conversions"
        if not data.get("formats"):
            data["formats"] = ["static"]
        if not str(data.get("cta") or "").strip() and edm_raw:
            data["cta"] = str(edm_raw[0].get("cta") or "").strip()[:80]
        variants_raw = edm_raw
    elif len(organic_raw) >= 2:
        logger.info(
            "Strategy MD: detected %s ORGANIC POST sections — using deterministic parse + Gemini brief metadata",
            len(organic_raw),
        )
        try:
            data = await _llm_parse_brief_metadata(text, filename=filename)
        except Exception:
            logger.exception("Strategy brief metadata LLM failed; using heuristics")
            data = {}
        if not isinstance(data, dict):
            data = {}
        low = text.lower()
        if not str(data.get("brand_name") or "").strip() and "kantar" in low:
            data["brand_name"] = "KANTAR"
        if not str(data.get("industry") or "").strip():
            data["industry"] = "Health & Wellness" if "supplement" in low else ""
        if not str(data.get("niche") or "").strip():
            data["niche"] = "Supplements" if "supplement" in low else ""
        if not str(data.get("objective_id") or "").strip():
            data["objective_id"] = "awareness"
        if not data.get("formats"):
            data["formats"] = ["static"]
        tail_notes = text.split("**Organic posting**")[-1].strip() if "**Organic posting**" in text else ""
        if tail_notes and not str(data.get("notes") or "").strip():
            data["notes"] = _clean_md_block(tail_notes)[:1800]
        variants_raw = organic_raw
    else:
        response = client.chat.completions.create(
            model=parse_model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        f"Filename: {filename or 'strategy.md'}\n\n"
                        f"Strategy document:\n{excerpt}"
                    ),
                },
            ],
            max_tokens=12000,
            temperature=0.15,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        finish = ""
        try:
            finish = str(response.choices[0].finish_reason or "")
        except Exception:
            finish = ""
        try:
            data = _extract_json(raw)
        except json.JSONDecodeError:
            # Retry once with a tighter budget — long docs often truncate mid-JSON.
            logger.warning(
                "Strategy parse JSON failed on first pass (finish=%s len=%s model=%s); retrying compact",
                finish,
                len(raw),
                parse_model,
            )
            compact_system = (
                system
                + " CRITICAL: keep every string SHORT. prompt ≤ 100 chars, hook ≤ 80, "
                "message ≤ 140. Prefer fewer words over perfect prose. "
                "Emit EVERY organic post / static row / carousel card — never summarize to fewer variants."
            )
            response = client.chat.completions.create(
                model=parse_model,
                messages=[
                    {"role": "system", "content": compact_system},
                    {
                        "role": "user",
                        "content": (
                            f"Filename: {filename or 'strategy.md'}\n\n"
                            f"Strategy document:\n{excerpt[:16000]}"
                        ),
                    },
                ],
                max_tokens=12000,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            raw = (response.choices[0].message.content or "").strip()
            try:
                finish = str(response.choices[0].finish_reason or "")
            except Exception:
                finish = ""
            try:
                data = _extract_json(raw)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Strategy parse JSON failed after retry (finish=%s len=%s): %s",
                    finish,
                    len(raw),
                    raw[:400],
                )
                raise ValueError(
                    "Could not parse strategy document — the AI response was cut off. "
                    "Try again, or shorten the MD file slightly."
                ) from exc

        if not isinstance(data, dict):
            raise ValueError("Could not parse strategy document")

        variants_raw = data.get("variants") if isinstance(data.get("variants"), list) else []

    cta = str(data.get("cta") or "Learn More").strip()[:80]
    offer = str(data.get("offer") or "").strip()[:160]
    variants = [_normalize_variant(v, cta, offer) for v in variants_raw if isinstance(v, dict)]
    variants = [v for v in variants if v["prompt"] or v["hook"] or v["message"]]
    # Prefer deterministic EDM / ORGANIC POST structure over LLM invention.
    if len(edm_raw) >= 2 and len(edm_raw) >= len(variants):
        variants = [_normalize_variant(v, cta, offer) for v in edm_raw]
    elif len(organic_raw) >= 2 and len(organic_raw) >= len(variants):
        variants = [_normalize_variant(v, cta, offer) for v in organic_raw]
    # Prefer MD structure (CREATIVE 1/2/3… each with Card 1..N) over LLM invention.
    variants = _prefer_structured_creatives(text, variants, cta)
    # Fashion retail briefs: **Creative Direction N** → static photo ads (skip GIF/video).
    variants = _prefer_creative_directions(
        text,
        variants,
        campaign_cta=cta,
        campaign_offer=offer,
    )
    fashion_retail = _is_fashion_retail_doc(text, variants)
    if not variants:
        raise ValueError("No creative variants found in the strategy document")
    variants = _explode_carousel_variants(variants, cta)
    # Re-apply per-creative CTA after explode (index==total within each group).
    for v in variants:
        if (v.get("format") or "") != "carousel":
            if not str(v.get("cta") or "").strip():
                v["cta"] = cta
            continue
        try:
            idx = int(v.get("carousel_index") or 0)
            tot = int(v.get("carousel_total") or 0)
        except (TypeError, ValueError):
            continue
        if tot >= 2:
            v["cta"] = cta if idx >= tot else ""

    angles = []
    for v in variants:
        if v["ad_angle"] and v["ad_angle"] not in angles:
            angles.append(v["ad_angle"])
    extra_angles = [
        normalize_angle_id(str(a))
        for a in (data.get("hook_frameworks") or [])
    ]
    for a in extra_angles:
        if a and a not in angles:
            angles.append(a)

    formats = _clean_list(
        [_normalize_format(x) for x in (data.get("formats") or [])]
        + [v["format"] for v in variants],
        _FORMATS,
    )
    if not formats:
        formats = ["static"]
    if fashion_retail:
        formats = ["static"]
        # One ad angle per static creative for Generate AI.
        angle_ids = []
        for v in variants:
            a = str(v.get("ad_angle") or "").strip()
            if a and a not in angle_ids:
                angle_ids.append(a)
        if not angle_ids:
            angle_ids = list(_FASHION_RETAIL_ANGLES[: max(1, min(len(variants), 6))])
        angles = angle_ids
    placements = _clean_list(data.get("placements") or [], _PLACEMENTS)
    if not placements:
        if "reel" in formats:
            placements = ["reels", "stories"]
        else:
            placements = ["feed"]

    count = max(1, min(_MAX_STRATEGY_VARIANTS, len(variants)))
    variants = variants[:_MAX_STRATEGY_VARIANTS]
    notes = str(data.get("notes") or "").strip()
    if len(notes) > 1800:
        notes = notes[:1800]

    # MD scenes stay on variants as knowledge. Copy is written on Generate AI.

    return {
        "brand_name": str(data.get("brand_name") or "").strip()[:120],
        "industry": str(data.get("industry") or "").strip()[:80] or (
            "Fashion Retail" if fashion_retail else ""
        ),
        "niche": str(data.get("niche") or "").strip()[:120] or (
            "New Arrivals" if fashion_retail else ""
        ),
        "geography": _map_geo(str(data.get("geography") or "")),
        "age_range": str(data.get("age_range") or "").strip()[:40],
        "audience_type": str(data.get("audience_type") or "").strip()[:120],
        "languages": str(data.get("languages") or "English").strip()[:40] or "English",
        "objective_id": _map_objective(str(data.get("objective_id") or "")),
        "cta": cta,
        "offer": offer,
        "product_name": str(data.get("product_name") or "").strip()[:120],
        "ad_copy_tone": str(data.get("ad_copy_tone") or "").strip()[:80],
        "placements": placements,
        "formats": formats,
        "hook_frameworks": angles,
        "target_variant_count": count,
        "notes": notes,
        "reasoning": str(data.get("reasoning") or "").strip()[:400],
        "filename": filename,
        "variants": variants[:_MAX_STRATEGY_VARIANTS],
        "image_aspect_ratio": (
            str(variants[0].get("aspect_ratio") or "1:1")
            if fashion_retail and variants
            else ("4:3" if fashion_retail else "")
        ),
        "creative_style": "fashion_retail_promo" if fashion_retail else "",
    }
