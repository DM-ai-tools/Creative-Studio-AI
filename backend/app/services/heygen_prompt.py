"""Map brief + HeyGen UI settings into Video Agent (v3) prompts."""

from __future__ import annotations

import re

from app.services.australian_copy import AUSTRALIAN_HEYGEN_VOICE_RULE
SCENE_ENVIRONMENT: dict[str, str] = {
    "neutral_studio": (
        "Professional broadcast studio with soft key light and shallow depth of field — "
        "subtle tech-agency office backdrop with blurred monitors. NOT a home, kitchen, or cafe."
    ),
    "coffee_shop": "Warm coffee shop interior, natural window light, lifestyle realism.",
    "office": (
        "Professional digital marketing / IT / performance agency office — glass-walled conference room, "
        "modern tech workspace with monitors, natural light. NEVER kitchen, bathroom, cafe, or suburban home."
    ),
    "outdoor": "Outdoor natural daylight — street or park appropriate to the industry.",
}

PRESENTER_RESIDENTIAL_FORBIDDEN_RULE = (
    "FORBIDDEN backgrounds: kitchen, bathroom, bedroom, living room, dining room, suburban home, "
    "apartment couch, cafe, coffee shop, restaurant, bar, backyard, or any domestic setting — "
    "unless the brief explicitly requests it."
)

BROLL_FULL_FRAME_RULES = (
    "B-ROLL / CUTAWAY (mandatory): Every insert MUST be a real VIDEO CLIP with visible motion "
    "(people moving, camera pan, walking, typing, product in use, screen scrolling). "
    "FORBIDDEN: static photographs, still images, frozen frames, Ken Burns on photos, "
    "slideshows, posters, flat charts, or any non-moving picture inside the video. "
    "Full-frame edge-to-edge only — no split-screen, half photo half graph, or collage. "
    "For stats: full-screen motion graphic or lower-third text — not a still image."
)

BROLL_PORTRAIT_ORIENTATION_RULE = (
    "B-ROLL ASPECT (9:16 mandatory): Output is vertical portrait. Every B-roll clip MUST be "
    "shot and framed in 9:16 vertical — subject fills the full height and width edge-to-edge. "
    "FORBIDDEN: inserting horizontal 16:9 landscape clips inside the portrait frame with black "
    "bars above/below (letterboxing). FORBIDDEN: placing captions or headlines in empty black "
    "bars — text belongs on the video content in the lower third only. "
    "If stock footage is landscape, crop/zoom it to fill 9:16 before inserting — never show bars."
)

BROLL_LANDSCAPE_ORIENTATION_RULE = (
    "B-ROLL ASPECT (16:9 mandatory): Output is horizontal landscape. Every B-roll clip MUST fill "
    "the full 16:9 frame edge-to-edge. FORBIDDEN: a small clip floating on a large black canvas "
    "(windowboxing). FORBIDDEN: vertical 9:16 clips with side bars (pillarboxing) "
    "or any letterboxing inside the frame. Crop/zoom stock footage to fill 16:9 before inserting."
)

HEYGEN_FORBID_STATS_GRAPHICS_RULE = (
    "NO STATS / DASHBOARD GRAPHICS IN RENDER (mandatory): Never show analytics dashboards, "
    "ROAS/ROI screenshots, performance charts, metric overlays, corner picture-in-picture stats, "
    "zoomed graphs, or any still performance image anywhere in the video — not during proof, CTA, "
    "or any other beat. Keep the presenter full frame on camera for the entire runtime. "
    "[INSERT … STAT IMAGE] script markers are post-production only — ignore them visually. "
    "Stats dashboards are added after render; your output must be presenter + motion B-roll only."
)

BROLL_STATS_POSTPROCESS_RULES = (
    "B-ROLL / CUTAWAY: Real VIDEO CLIP inserts with visible motion only. "
    "FORBIDDEN: any dashboard, chart, graph, analytics screen, metric overlay, corner stat box, "
    "picture-in-picture screenshot, or still performance image. Presenter stays full frame during "
    "proof and results lines — stats are added in post-production, not by you."
)

MOTION_VIDEO_ONLY_RULE = (
    "NO STILL IMAGES IN THE VIDEO: The final output must be 100% motion video — "
    "presenter footage and moving B-roll clips only. Never insert a static photo, "
    "illustration, or motionless graphic as a 'clip'."
)

BROLL_AUDIENCE_RULE = (
    "B-ROLL PEOPLE (mandatory): Any business owner, client, or customer shown in B-roll must look "
    "like a successful entrepreneur, CEO, founder, or high-net-worth professional — "
    "well-dressed, confident, modern office or high-end environment. "
    "FORBIDDEN in B-roll: small bakery owners, boutique retail shops, market stalls, "
    "tradespeople in overalls, cheap-looking offices, or any imagery that suggests a small "
    "struggling micro-business. Target audience is ambitious growth-focused business owners."
)

BROLL_HINTS: dict[str, str] = {
    "directed": (
        "B-ROLL IS USER-DIRECTED ONLY (mandatory): Use ONLY the SCRIPT-TO-VIDEO SYNC MAP and "
        "SCENE B-ROLL DIRECTIONS below. Do NOT invent, improvise, or randomly pick B-roll. "
        "If a beat says presenter on camera, show presenter — no cutaway. "
        "If a beat specifies B-roll, show exactly that shot — no substitutes."
    ),
    "auto": (
        "Between talking-head beats, insert full-frame B-roll only: "
        "successful business owners at laptops in premium offices, confident CEOs in meetings, "
        "high-performing teams, modern workspaces, digital dashboards in motion — "
        "one cohesive shot per cut matching the script topic."
    ),
    "product": (
        "Insert full-frame product/service B-roll: digital product in use, high-end client moments, "
        "results dashboards, confident professional environments — each clip fills the entire frame."
    ),
    "none": "Talking-head only; minimal cuts; keep focus on the presenter.",
}

BROLL_NO_RANDOM_RULE = (
    "NO RANDOM B-ROLL (mandatory): Never choose stock footage on your own. Every cut must follow "
    "the SCRIPT-TO-VIDEO SYNC MAP beat-by-beat. Forbidden: unrelated offices, random people, "
    "generic charts, or cuts that do not match the spoken line. When unsure, keep presenter on camera."
)

MUSIC_HINTS: dict[str, str] = {
    "upbeat_acoustic": "Light upbeat acoustic background music under dialogue.",
    "soft_ambient": "Soft ambient bed under dialogue; do not overpower speech.",
    "none": "No background music.",
}

# HeyGen Video Agent often places headline banners over the face unless explicitly constrained.
TEXT_SAFE_ZONE_RULE = (
    "⚠ ABSOLUTE RULE — ON-SCREEN TEXT (applies to every single frame): "
    "ZERO text, banners, headlines, badges, or overlays are permitted over the presenter's face, "
    "forehead, hair, eyes, nose, or mouth — ever. "
    "DO NOT place a coloured banner (orange, black, or any colour) across the top of the frame "
    "while the avatar is visible — this cuts the presenter's head in half and is FORBIDDEN. "
    "The ONLY permitted text zones are: "
    "(1) LOWER THIRD — bottom 25% of frame, below the chin; "
    "(2) END CARD frames where the avatar is not present. "
    "Spoken-word captions: bottom-center only, never above mid-frame. "
    "If you need to show a headline stat ('95% of people…'), use a DEDICATED full-screen text card "
    "with NO avatar visible — cut away from the presenter first, show the stat frame alone, "
    "then cut back. NEVER overlay it on top of a talking head."
)

# HeyGen POST /v3/video-agents — prompt field max 10,000 characters
HEYGEN_V3_PROMPT_MAX = 10_000

TEXT_PLACEMENT_SHORT = (
    "On-screen text: lower third or thin top strip only; never over the presenter's face or eyes."
)

# HeyGen Video Agent often merges TONE + BRAND metadata into a persistent top-left banner
# (e.g. tone "Professional" + brand "ClickTrends" → "Professional ClickTrends").
BRAND_BADGE_FORBIDDEN_RULE = (
    "FORBIDDEN ON-SCREEN ARTEFACTS (hard rules — no exceptions): "
    "(a) BRAND BADGES: Never place a persistent corner watermark, top-left banner, "
    "or any overlay that shows the brand name as a static badge throughout the video. "
    "The brand name may only appear as part of a spoken caption at the bottom. "
    "(b) TONE PREFIX: Never combine the ad tone or any adjective with the brand name "
    "in on-screen text — e.g. 'Professional ClickTrends', 'Expert ClickTrends' are "
    "strictly forbidden; use only the exact brand name 'ClickTrends'. "
    "(c) DOUBLE TEXT: Never show both a large headline card AND a subtitle caption on "
    "the same frame — only one text layer at a time. During B-roll beats, show ONLY "
    "the spoken word caption at the bottom; do NOT add a separate title card on top."
)


def brand_onscreen_text_rule(brand: str, *, tone: str | None = None) -> str:
    """Exact brand spelling for any on-screen label — tone is voice-only, not a headline prefix."""
    brand = (brand or "the brand").strip()
    tone_note = ""
    if tone and tone.strip():
        tone_note = (
            f' The ad tone "{tone.strip()}" guides voice delivery ONLY — '
            f'never display it on screen and never prefix the brand with it '
            f'(forbidden example: "{tone.strip()} {brand}").'
        )
    return (
        f'BRAND ON-SCREEN TEXT (mandatory): If on-screen text includes the brand, '
        f'use exactly "{brand}" — same spelling, no extra words before or after.{tone_note}'
    )


def strip_insert_stat_placeholders(text: str) -> str:
    """Remove [INSERT … STAT IMAGE] lines — post-production only, must not reach HeyGen."""
    if not text or not str(text).strip():
        return text or ""
    out: list[str] = []
    for line in str(text).splitlines():
        if re.match(r"^\s*\[INSERT\b", line, re.I):
            continue
        cleaned = re.sub(r"\[INSERT\b[^\]]*\]", "", line, flags=re.I).strip()
        if cleaned:
            out.append(cleaned)
    if not out:
        return re.sub(r"\[INSERT\b[^\]]*\]", "", str(text), flags=re.I).strip()
    return "\n".join(out)


def sanitize_production_skeleton_for_heygen(
    skeleton: str,
    *,
    brand: str,
    tone: str | None = None,
) -> str:
    """Strip HeyGen skeleton of patterns that produce bad on-screen artefacts:

    • Tone-prefixed brand banners  ("Professional ClickTrends")
    • Dashboard / stats overlay commands  (added in post-production via ffmpeg)
    • Double-text: large headline cards on B-roll beats  (only captions allowed)
    """
    text = strip_insert_stat_placeholders(skeleton.strip())
    if not text:
        return text

    brand = (brand or "").strip()
    tone_val = (tone or "").strip()

    # ── 1. Remove stats / dashboard overlay commands ──────────────────────────
    text = re.sub(
        r"(?i)(show|display|insert|overlay|full[- ]screen).{0,40}(dashboard|stats?|roas|roi|analytics|screenshot)",
        "Presenter on camera full frame — stats added in post-production",
        text,
    )

    # ── 2. Convert TONE metadata → voice-only note (never show on screen) ──────
    text = re.sub(
        r"^TONE:\s*.+$",
        f"VOICE DELIVERY (spoken style only — never show on screen): {tone_val or 'conversational'}",
        text,
        count=1,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    # ── 3. Strip tone-prefixed brand from any On-Screen Text field ────────────
    # Pattern: "Professional ClickTrends" or "Conversational ClickTrends" etc.
    if brand and tone_val:
        # Replace "ToneWord Brand" → just "Brand" in on-screen text lines
        text = re.sub(
            rf"(?i)(?<![a-zA-Z]){re.escape(tone_val)}\s+{re.escape(brand)}(?![a-zA-Z])",
            brand,
            text,
        )
        # Also catch "Tone | Brand" style (pipe-separated banners)
        text = re.sub(
            rf"(?i){re.escape(tone_val)}\s*[|:]\s*{re.escape(brand)}",
            brand,
            text,
        )

    # ── 4. Strip persistent top-left brand watermark lines from the skeleton ──
    # HeyGen reads "On-Screen Text: Professional ClickTrends" and places it as
    # a permanent corner badge. Replace any such line with an empty marker.
    if brand:
        # Remove lines that set a brand badge / persistent watermark
        text = re.sub(
            rf"(?im)^(on[- ]screen\s+text|brand\s+badge|watermark|banner)[^:]*:\s*.*{re.escape(brand)}.*$",
            f"# (brand badge removed — use exact brand name only in spoken references)",
            text,
        )
        # Add explicit brand spelling note once
        marker = f"BRAND: {brand}"
        if marker in text and "ON-SCREEN BRAND TEXT" not in text:
            text = text.replace(
                marker,
                f"{marker}\nON-SCREEN BRAND TEXT (exact spelling only, no prefix): {brand}",
                1,
            )

    # ── 5. Suppress large headline cards during B-roll beats ─────────────────
    # Pattern: any On-Screen Text that appears inside a B-roll / scene block
    # Replace with a caption-only note so only spoken word captions appear.
    text = re.sub(
        r"(?im)^(on[- ]screen\s+text)[^:]*:\s+[A-Z][A-Z\s]{15,}$",
        r"\1: [caption only — no separate headline card]",
        text,
    )

    return text

NATURAL_COLOR_RULE = (
    "COLOUR (mandatory): Photorealistic natural skin tones on every person — healthy RGB, "
    "no blue/teal/orange skin tint, no 'color grade' on faces, no desaturated black crush. "
    "Environment may be slightly cooler in problem scenes but people must look human and natural. "
    "Talking-head scenes: neutral white balance, broadcast-safe contrast, true-to-life colours."
)

HEYGEN_IN_VIDEO_CAPTION_RULE = (
    "BURNED-IN SUBTITLES DURING RENDER (mandatory): While this video is being produced, "
    "show every word the presenter speaks as on-screen captions — large white sans-serif, "
    "thick black outline, bottom-center safe zone (bottom 20%), synced to lip-sync. "
    "Use the exact words from SPOKEN SCRIPT only. Never cover the face, eyes, or forehead. "
    "Highlight product names and CTA lines in brand accent colour when spoken."
)

SCRIPT_VISUAL_SYNC_RULE = (
    "SCRIPT-TO-VIDEO SYNC (mandatory): The presenter MUST speak the SPOKEN SCRIPT word-for-word "
    "(lip-sync). Every cut, B-roll insert, on-screen text line, and FACIAL EXPRESSION must match "
    "what is being said in that same beat — never show unrelated footage or a mismatched mood "
    "(e.g. smiling while describing a problem). "
    "Cut only on sentence boundaries. When the script mentions a product, problem, or offer, "
    "the visual at that moment must show that exact topic. Follow the SCRIPT-TO-VIDEO SYNC MAP "
    "beat-by-beat before improvising any extra shots."
)

AVATAR_EXPRESSION_SYNC_RULE = (
    "AVATAR FACIAL EXPRESSION (mandatory): Match emotion to each spoken line — NEVER use a "
    "constant smile throughout. Problem/pain lines: concerned, serious, empathetic (no smile). "
    "Hook/questions: curious or provocative (no default grin). Solution/benefit lines: relieved "
    "then confident (smile only when words are genuinely positive). Proof: assured, credible. "
    "CTA: warm inviting close — light smile acceptable only on the final uplifting beat. "
    "Change expression at every beat boundary; follow EXPRESSION cues in the sync map."
)

_PAIN_WORDS = (
    "struggle", "waste", "wasting", "problem", "frustrat", "losing", "stress", "stressed",
    "pain", "fail", "failed", "can't", "cannot", "nobody", "wrong", "stuck", "bleeding",
    "anxious", "worry", "worried", "difficult", "hard", "alone", "exhaust", "tired",
)
_POSITIVE_WORDS = (
    "finally", "discover", "solution", "help", "helps", "easy", "results", "transform",
    "grow", "growth", "win", "winning", "success", "confident", "better", "improve",
)
_PROOF_WORDS = ("%", "proven", "clients", "customers", "roi", "leads", "booked", "trusted")
_CTA_WORDS = ("book", "click", "call", "now", "today", "free", "start", "join", "get", "claim")


def infer_avatar_expression_for_line(
    say: str,
    *,
    beat_index: int = 0,
    total_beats: int = 1,
) -> str:
    """Heuristic expression direction from spoken line content and story position."""
    t = say.lower().strip()
    if any(w in t for w in _PAIN_WORDS):
        return "Concerned / empathetic — furrowed brow, serious face, NO smile"
    if beat_index == 0 and ("?" in say or any(w in t for w in ("did you", "are you", "what if", "ever"))):
        return "Curious or provocative hook — attentive, slight concern, NO default smile"
    if any(w in t for w in _POSITIVE_WORDS):
        return "Relieved then confident — engaged eyes; smile only on clearly positive words"
    if any(w in t for w in _PROOF_WORDS):
        return "Assured and credible — steady nod, subtle confident smile at most"
    if beat_index >= max(total_beats - 1, 0) or any(w in t for w in _CTA_WORDS):
        return "Warm CTA close — inviting tone, gentle smile on final uplifting phrase only"
    progress = beat_index / max(total_beats - 1, 1)
    if progress < 0.3:
        return "Serious hook delivery — direct eye contact, neutral-to-concerned, no grin"
    if progress < 0.55:
        return "Empathetic concern — mirror pain described, frustrated or worried, NO smiling"
    if progress < 0.8:
        return "Building confidence — posture opens; smile only when line turns positive"
    return "Warm but authentic — expression follows words, not a frozen smile"


_SPOKEN_SCRIPT_RE = re.compile(
    r"(SPOKEN SCRIPT[^\n]*\n)(.*?)(?=\n(?:MANDATORY SPOKEN|STATS DASHBOARD|SCENE B-ROLL|SCRIPT-TO-VIDEO|Ad hook:|PRODUCTION SCRIPT))",
    re.DOTALL | re.IGNORECASE,
)
_MANDATORY_FIGURES_RE = re.compile(
    r"(MANDATORY SPOKEN FIGURES[^\n]*\n.*?)(?=\n(?:STATS DASHBOARD|SCENE B-ROLL|SCRIPT-TO-VIDEO|Ad hook:|PRODUCTION SCRIPT))",
    re.DOTALL | re.IGNORECASE,
)


def clamp_heygen_v3_prompt(prompt: str, max_len: int = HEYGEN_V3_PROMPT_MAX) -> str:
    """Fit HeyGen Video Agent prompt under API limit.

  Spoken script + mandatory OCR figures are NEVER truncated — trim B-roll/sync/
  production skeleton instead so proof numbers in the second half still reach HeyGen.
    """
    text = prompt.strip()
    if len(text) <= max_len:
        return text

    spoken_match = _SPOKEN_SCRIPT_RE.search(text)
    mandatory_match = _MANDATORY_FIGURES_RE.search(text)
    spoken_block = spoken_match.group(0) if spoken_match else ""
    mandatory_block = mandatory_match.group(0) if mandatory_match else ""
    protected = spoken_block + mandatory_block

  # Strip protected dialogue blocks, aggressively trim the rest, then reinsert.
    scratch = text
    if mandatory_block:
        scratch = scratch.replace(mandatory_block, "", 1)
    if spoken_block:
        scratch = scratch.replace(spoken_block, "", 1)

    prod_marker = "PRODUCTION SCRIPT (timing, scene cuts, on-screen text, colour grade):\n"
    sync_marker = "SCRIPT-TO-VIDEO SYNC MAP"
    for marker, floor in ((sync_marker, 400), (prod_marker, 600)):
        if marker in scratch and len(scratch) + len(protected) > max_len:
            idx = scratch.find(marker)
            if idx < 0:
                continue
            if marker == prod_marker:
                head, rest = scratch[:idx], scratch[idx + len(marker) :]
                budget = max(
                    floor,
                    max_len - len(head) - len(protected) - len(marker) - 120,
                )
                if len(rest) > budget:
                    rest = rest[:budget].rsplit("\n", 1)[0] + "\n[Production script truncated.]\n"
                scratch = head + marker + rest
            else:
                end_idx = scratch.find(prod_marker, idx + len(marker))
                if end_idx < 0:
                    end_idx = len(scratch)
                head = scratch[:idx]
                body = scratch[idx:end_idx]
                tail = scratch[end_idx:]
                budget = max(floor, max_len - len(head) - len(tail) - len(protected) - 80)
                if len(body) > budget:
                    body = body[:budget].rsplit("\n", 1)[0] + "\n[Sync map truncated.]\n"
                scratch = head + body + tail

    if prod_marker in scratch and len(scratch) + len(protected) > max_len:
        head, rest = scratch.split(prod_marker, 1)
        budget = max(600, max_len - len(head) - len(protected) - len(prod_marker) - 120)
        if len(rest) > budget:
            rest = rest[:budget].rsplit("\n", 1)[0] + "\n[Production script truncated.]\n"
        scratch = f"{head}{prod_marker}{rest}"

    # Reassemble: intro + protected dialogue + trimmed tail (under budget).
    insert_at = 0
    if spoken_match:
        insert_at = spoken_match.start()
    rebuilt = scratch[:insert_at].rstrip() + "\n" + protected + "\n" + scratch[insert_at:].lstrip()
    rebuilt = re.sub(r"\n{3,}", "\n\n", rebuilt).strip()

    if len(rebuilt) <= max_len:
        return rebuilt

    # Last resort: shorten only the non-dialogue intro (never touch spoken/mandatory).
    intro = rebuilt[:insert_at].strip()
    tail = rebuilt[insert_at + len(protected) :].strip()
    intro_budget = max(800, max_len - len(protected) - len(tail) - 100)
    if len(intro) > intro_budget:
        intro = intro[:intro_budget].rsplit("\n", 1)[0] + "\n[Intro trimmed for HeyGen limit.]\n"
    rebuilt = f"{intro}\n{protected}\n{tail}".strip()
    if len(rebuilt) <= max_len:
        return rebuilt

    return rebuilt[: max_len - 60].rstrip() + "\n[Prompt trimmed to HeyGen 10,000 character limit.]"


def resolve_text_placement_rules() -> str:
    return TEXT_SAFE_ZONE_RULE


def _heygen_settings(brief: dict) -> dict:
    raw = brief.get("heygen_settings")
    if isinstance(raw, dict):
        return raw
    kb = brief.get("key_benefits")
    if isinstance(kb, dict) and isinstance(kb.get("heygen_settings"), dict):
        return kb["heygen_settings"]
    return {}


def broll_orientation_rule(format_type: str) -> str:
    """Format-specific rule — stops HeyGen inserting landscape B-roll inside portrait reels."""
    ft = (format_type or "").lower()
    if ft in {"reel", "stories"}:
        return BROLL_PORTRAIT_ORIENTATION_RULE
    if ft == "video":
        return BROLL_LANDSCAPE_ORIENTATION_RULE
    return ""


def resolve_aspect_ratio_label(heygen: dict, format_type: str) -> str:
    """Creative format wins over stored HeyGen card aspect (avoids 9:16 prompt + landscape API)."""
    ft = (format_type or "").lower()
    if ft in {"reel", "stories"}:
        return "9:16 portrait (vertical)"
    if ft == "video":
        return "16:9 landscape (horizontal)"
    custom = str(heygen.get("aspect_ratio_custom") or "").strip()
    if custom:
        return custom
    label = str(heygen.get("aspect_ratio_label") or heygen.get("aspect_ratio") or "").strip()
    if label:
        return label
    return "1:1 square"


def resolve_background_direction(brief: dict, heygen: dict) -> str:
    industry = (
        brief.get("target_industry_label")
        or brief.get("target_industry_id")
        or brief.get("product_name")
        or "the client's industry"
    )
    custom_scene = str(heygen.get("scene_custom") or "").strip()
    if custom_scene:
        base = custom_scene
    else:
        scene_id = str(heygen.get("scene") or "office").strip()
        label = str(heygen.get("scene_label") or "").strip()
        base = label or SCENE_ENVIRONMENT.get(scene_id, SCENE_ENVIRONMENT["office"])

    objective = str(brief.get("objective") or "").strip()
    notes = ""
    kb = brief.get("key_benefits")
    if isinstance(kb, dict) and kb.get("notes"):
        notes = str(kb["notes"])[:400]

    parts = [
        f"Primary environment: {base}",
        f"Every scene background must feel like a real {industry} setting — photorealistic, "
        "natural lighting, believable props. Avoid flat color fills, cartoon look, or obvious AI artifacts.",
        PRESENTER_RESIDENTIAL_FORBIDDEN_RULE,
    ]
    if objective:
        parts.append(f"Campaign objective: {objective}")
    if notes:
        parts.append(f"Brief notes: {notes}")
    return " ".join(parts)


def resolve_visual_style(
    brief: dict,
    heygen: dict,
    *,
    for_video_agent: bool = False,
    format_type: str = "",
) -> str:
    primary = brief.get("primary_color") or ""
    secondary = brief.get("secondary_color") or ""
    brand = brief.get("brand_name") or brief.get("product_name") or "the brand"
    color_line = ""
    if primary or secondary:
        color_line = f" Brand palette: primary {primary}, secondary {secondary}."

    broll_id = str(heygen.get("broll_insert") or "directed").strip()
    music_id = str(heygen.get("music") or "upbeat_acoustic").strip()
    broll = str(heygen.get("broll_insert_label") or BROLL_HINTS.get(broll_id, BROLL_HINTS["directed"]))
    music = str(heygen.get("music_label") or MUSIC_HINTS.get(music_id, ""))

    camera = (
        heygen.get("camera_framing_label")
        or heygen.get("camera_framing_custom")
        or heygen.get("camera_framing")
        or "Medium close-up"
    )
    delivery = (
        heygen.get("delivery_style_label")
        or heygen.get("delivery_style_custom")
        or heygen.get("delivery_style")
        or "Conversational"
    )
    visual_cues = str(heygen.get("visual_cues") or "").strip()
    if for_video_agent and len(visual_cues) > 600:
        visual_cues = visual_cues[:600].rsplit(" ", 1)[0] + "…"

    bits = [
        f"Style for {brand}: cinematic Meta ad, photorealistic humans and environments.{color_line}",
        f"Camera: {camera}. Delivery: {delivery}.",
        AUSTRALIAN_HEYGEN_VOICE_RULE,
        AVATAR_EXPRESSION_SYNC_RULE,
        MOTION_VIDEO_ONLY_RULE,
        BROLL_FULL_FRAME_RULES,
        broll_orientation_rule(format_type),
        BROLL_AUDIENCE_RULE,
        broll,
        music,
    ]
    if broll_id == "directed" or str(heygen.get("scene_broll_directions") or "").strip():
        bits.append(BROLL_NO_RANDOM_RULE)
    if visual_cues:
        bits.append(f"Additional visual direction: {visual_cues}")
    bits.append(NATURAL_COLOR_RULE)
    bits.append(BRAND_BADGE_FORBIDDEN_RULE)
    bits.append(brand_onscreen_text_rule(str(brand)))
    bits.append(resolve_text_placement_rules() if for_video_agent else TEXT_PLACEMENT_SHORT)
    return " ".join(bits)
