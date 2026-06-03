"""Map brief + HeyGen UI settings into Video Agent (v3) prompts."""

from __future__ import annotations

# Scene ids from frontend/lib/heygenOptions.ts
SCENE_ENVIRONMENT: dict[str, str] = {
    "neutral_studio": (
        "Professional studio with soft key light and shallow depth of field — "
        "not a flat solid-color backdrop."
    ),
    "coffee_shop": "Warm coffee shop interior, natural window light, lifestyle realism.",
    "office": "Modern bright office with glass, plants, and natural light — corporate but human.",
    "outdoor": "Outdoor natural daylight — street or park appropriate to the industry.",
}

BROLL_FULL_FRAME_RULES = (
    "B-ROLL / CUTAWAY (mandatory): Every insert MUST be a real VIDEO CLIP with visible motion "
    "(people moving, camera pan, walking, typing, product in use, screen scrolling). "
    "FORBIDDEN: static photographs, still images, frozen frames, Ken Burns on photos, "
    "slideshows, posters, flat charts, or any non-moving picture inside the video. "
    "Full-frame edge-to-edge only — no split-screen, half photo half graph, or collage. "
    "For stats: full-screen motion graphic or lower-third text — not a still image."
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
    "(lip-sync). Every cut, B-roll insert, and on-screen text line must match what is being said "
    "in that same beat — never show unrelated footage while the avatar discusses something else. "
    "Cut only on sentence boundaries. When the script mentions a product, problem, or offer, "
    "the visual at that moment must show that exact topic. Follow the SCRIPT-TO-VIDEO SYNC MAP "
    "beat-by-beat before improvising any extra shots."
)


def clamp_heygen_v3_prompt(prompt: str, max_len: int = HEYGEN_V3_PROMPT_MAX) -> str:
    """Fit HeyGen Video Agent prompt under API limit; keep spoken script, trim skeleton tail."""
    text = prompt.strip()
    if len(text) <= max_len:
        return text

    prod_marker = "PRODUCTION SCRIPT (timing, scene cuts, on-screen text, colour grade):\n"
    sync_idx = text.find("SCRIPT-TO-VIDEO SYNC MAP")
    if sync_idx >= 0 and prod_marker in text and len(text) > max_len:
        prod_idx = text.find(prod_marker, sync_idx)
        if prod_idx > sync_idx:
            head = text[:sync_idx]
            sync_body = text[sync_idx:prod_idx]
            tail = text[prod_idx:]
            sync_budget = min(1400, max(500, max_len - len(head) - len(tail) - 200))
            if len(sync_body) > sync_budget:
                sync_body = sync_body[:sync_budget].rsplit("\n", 1)[0] + "\n"
            text = head + sync_body + tail

    marker = prod_marker
    if marker in text:
        head, rest = text.split(marker, 1)
        budget = max_len - len(head) - 120
        if budget > 400:
            trimmed = rest[:budget].rstrip()
            text = (
                f"{head}{marker}{trimmed}\n"
                "[Production script truncated for HeyGen 10k prompt limit.]"
            )

    if len(text) <= max_len:
        return text

    spoken_marker = "SPOKEN SCRIPT: "
    if spoken_marker in text:
        parts = text.split(spoken_marker, 1)
        head = parts[0] + spoken_marker
        tail = parts[1]
        next_section = tail.find("\n")
        if next_section > 0:
            spoken = tail[:next_section]
            remainder = tail[next_section:]
            spoken_budget = max(400, max_len - len(head) - len(remainder) - 200)
            if len(spoken) > spoken_budget:
                spoken = spoken[:spoken_budget].rsplit(" ", 1)[0] + "…"
            text = head + spoken + remainder

    if len(text) <= max_len:
        return text

    return text[: max_len - 60].rstrip() + "\n[Prompt trimmed to HeyGen 10,000 character limit.]"


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


def resolve_aspect_ratio_label(heygen: dict, format_type: str) -> str:
    custom = str(heygen.get("aspect_ratio_custom") or "").strip()
    if custom:
        return custom
    label = str(heygen.get("aspect_ratio_label") or heygen.get("aspect_ratio") or "").strip()
    if label:
        return label
    if format_type in {"reel", "stories"}:
        return "9:16 portrait (vertical)"
    if format_type == "video":
        return "16:9 landscape (horizontal)"
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
        scene_id = str(heygen.get("scene") or "neutral_studio").strip()
        label = str(heygen.get("scene_label") or "").strip()
        base = label or SCENE_ENVIRONMENT.get(scene_id, SCENE_ENVIRONMENT["neutral_studio"])

    objective = str(brief.get("objective") or "").strip()
    notes = ""
    kb = brief.get("key_benefits")
    if isinstance(kb, dict) and kb.get("notes"):
        notes = str(kb["notes"])[:400]

    parts = [
        f"Primary environment: {base}",
        f"Every scene background must feel like a real {industry} setting — photorealistic, "
        "natural lighting, believable props. Avoid flat color fills, cartoon look, or obvious AI artifacts.",
    ]
    if objective:
        parts.append(f"Campaign objective: {objective}")
    if notes:
        parts.append(f"Brief notes: {notes}")
    return " ".join(parts)


def resolve_visual_style(brief: dict, heygen: dict, *, for_video_agent: bool = False) -> str:
    primary = brief.get("primary_color") or ""
    secondary = brief.get("secondary_color") or ""
    brand = brief.get("brand_name") or brief.get("product_name") or "the brand"
    color_line = ""
    if primary or secondary:
        color_line = f" Brand palette: primary {primary}, secondary {secondary}."

    broll_id = str(heygen.get("broll_insert") or "auto").strip()
    music_id = str(heygen.get("music") or "upbeat_acoustic").strip()
    broll = str(heygen.get("broll_insert_label") or BROLL_HINTS.get(broll_id, BROLL_HINTS["auto"]))
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
        MOTION_VIDEO_ONLY_RULE,
        BROLL_FULL_FRAME_RULES,
        BROLL_AUDIENCE_RULE,
        broll,
        music,
    ]
    if visual_cues:
        bits.append(f"Additional visual direction: {visual_cues}")
    bits.append(NATURAL_COLOR_RULE)
    bits.append(resolve_text_placement_rules() if for_video_agent else TEXT_PLACEMENT_SHORT)
    return " ".join(bits)
