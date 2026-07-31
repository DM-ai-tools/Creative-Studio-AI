"""Generate detailed AI image generation prompts from brief context.

Architecture
------------
1. select_and_build_image_plan(brief, brand)
   LLM step 1 – reads campaign context, selects the 1-3 best use cases.
   LLM step 2 – builds a photorealistic image generation prompt from those use cases.
   Returns ImagePlan with use_cases, prompt, reasoning.

2. generate_image_prompt(data)
   Legacy/manual path: user supplied context → AI builds prompt.
   Still used by the /generation/image-prompt API for frontend preview.
"""

from __future__ import annotations

import json
import logging
import random
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_USE_CASE_DESCRIPTIONS: dict[str, str] = {
    # ── Emotional / Brand Imagery ─────────────────────────────────────────────
    "hero_product": (
        "hero product shot — clean product centred on a brand-appropriate background, "
        "studio lighting, sharp focus, minimal props, premium feel"
    ),
    "lifestyle": (
        "lifestyle scene — product naturally integrated into a real-life environment, "
        "warm natural lighting, authentic human context, aspirational yet relatable"
    ),
    "product_vibe": (
        "mood & vibe shot — product placed to evoke a specific atmosphere or emotion, "
        "creative styling, strong colour palette, environment tells the brand story"
    ),
    "product_person": (
        "product with person — real human interacting with the product, "
        "genuine expression, natural body language, shallow depth of field, "
        "face or hands as focal point alongside the product"
    ),
    "feature_explanation": (
        "feature callout — close-up or annotated view highlighting a specific product feature, "
        "clean background, clear visual hierarchy, benefit-driven composition"
    ),
    # ── Functional / Conversion Imagery ──────────────────────────────────────
    "material_composition": (
        "ingredients / materials flat lay — overhead or angled arrangement of raw materials, "
        "textures, or components; minimalist styling; crisp macro-level detail; "
        "subtle benefit callouts integrated naturally"
    ),
    "detail_texture": (
        "macro detail / texture close-up — extreme close-up showing craftsmanship, material quality, "
        "or surface texture; shallow depth of field; soft directional light revealing every detail"
    ),
    "size_scale": (
        "size and scale reference — product photographed next to a human hand or common everyday "
        "object to communicate exact proportions; neutral background; natural perspective"
    ),
    "multi_angle": (
        "multi-angle / 360-degree product view — multiple angles of the same product arranged in "
        "a single composition (front, side, back, top); consistent lighting; white or brand background"
    ),
    "color_swatch": (
        "colour and variant swatch grid — all available colours, finishes, or sizes displayed "
        "together in a clean grid or line-up; minimal background; equal lighting on each variant"
    ),
    "packaging_unbox": (
        "packaging and unboxing flat lay — product box and all included contents arranged neatly "
        "on a flat surface (top-down or slight angle); premium styling; brand colour palette"
    ),
    "comparison": (
        "comparison imagery — side-by-side visual contrasting this product against a competitor, "
        "previous version, or size chart; clear labels; benefit-forward layout"
    ),
    "platform_crop": (
        "platform-specific crop variant — composition designed for a specific ad placement: "
        "either square 1:1 feed, tall 9:16 Stories/Reels, or wide landscape web hero banner; "
        "key subject centred for safe-zone cropping"
    ),
    # ── Best Sellers — Emotional Layer ───────────────────────────────────────
    "bs_emotional_using": (
        "people genuinely using and enjoying the product — candid or semi-candid scene, "
        "authentic emotion (joy, satisfaction, relief), product is hero but person is the storyteller"
    ),
    "bs_explaining": (
        "person explaining or demonstrating the product — direct-to-camera or demonstration pose, "
        "clear product visibility, educational yet warm visual tone"
    ),
    "bs_ecosystem": (
        "product as part of the customer's daily ecosystem — product visible alongside complementary "
        "items the target audience already owns; tells a 'this fits your life' story"
    ),
    "bs_emotional_appeal": (
        "emotional buyer appeal — imagery that prioritises feeling over function: "
        "soft lighting, aspirational setting, expressive human subject, mood-first composition "
        "that makes the viewer feel something before they think"
    ),
    # ── Best Sellers — Utility & Audience ────────────────────────────────────
    "bs_real_life": (
        "real-life application — product solving a clear, relatable problem in an everyday context; "
        "realistic home, office, outdoor, or kitchen environment; natural documentary-style lighting"
    ),
    "bs_segments": (
        "audience segmentation — same product photographed in use by visibly different customer "
        "segments (age, lifestyle, profession); shows broad relevance without losing specificity"
    ),
    # ── Best Sellers — Decision Layer ────────────────────────────────────────
    "bs_price_feature": (
        "price, feature, colour, or spec highlight — close-up or callout-style image emphasising "
        "the single most compelling decision factor (price badge, key feature, colour finish, or spec detail)"
    ),
    "bs_emotion_decision": (
        "emotion-driven purchase decision — the moment of clarity or desire just before buying: "
        "aspirational setting, warm intimate light, subject expressing quiet confidence or satisfaction"
    ),
    "bs_envision": (
        "envisioning the need — imagery that makes the viewer picture their own life improved by "
        "the product; uses second-person visual language (empty space for the viewer to insert themselves)"
    ),
    "bs_skim_vs_buyer": (
        "dual-audience image — designed to stop a fast-scrolling skim-reader with a bold emotional cue "
        "(strong colour, striking face, or arresting composition) while also containing a spec or "
        "comparison detail for the serious buyer who pauses to look closer"
    ),
    "bs_artistic": (
        "artistic / editorial perspective — campaign-style creative image: unconventional angle, "
        "bold colour grading, cinematic lighting, or conceptual styling that elevates the product "
        "to a brand-story visual rather than a straight product shot"
    ),
    # ── Use Case Templates ────────────────────────────────────────────────────
    "virtual_tryon": (
        "virtual try-on AR mockup — photorealistic render of the product worn or placed in context "
        "(apparel on model, eyewear on face, furniture in room) as if viewed through an AR overlay; "
        "clean realistic lighting; true-to-life scale and perspective"
    ),
}

_RATIO_HINTS: dict[str, str] = {
    "1:1":    "square canvas, balanced composition, Instagram/Facebook feed optimised",
    "4:5":    "portrait canvas 4:5, strong vertical composition, Instagram portrait feed",
    "9:16":   "tall portrait 9:16 full-screen vertical, Reels/Stories/TikTok layout",
    "16:9":   "landscape 16:9, wide cinematic composition, website hero / YouTube",
    "1.91:1": "wide landscape 1.91:1, Facebook/Google ads banner layout",
    "2:3":    "portrait 2:3, Pinterest or print-ready layout",
}

# ── Use-case catalogue summary (sent to LLM for selection) ───────────────────
_USE_CASE_CATALOGUE = """
AVAILABLE IMAGE USE CASES (id → description):

EMOTIONAL / BRAND:
  hero_product       – clean studio product shot, brand background, premium feel
  lifestyle          – product in real-life setting, warm natural light, aspirational
  product_vibe       – product creating scene/mood, strong colour palette, atmospheric
  product_person     – real human interacting with product, sharp face, shallow DoF
  feature_explanation– close-up/annotated view of one key product feature

FUNCTIONAL / CONVERSION:
  material_composition – macro ingredients/materials flat lay, benefit callouts
  detail_texture       – extreme macro texture/craftsmanship close-up
  size_scale           – product next to hand or everyday object (scale reference)
  multi_angle          – multiple product angles in one clean composition
  color_swatch         – all colour/finish variants in a swatch grid
  packaging_unbox      – unboxing flat lay, all included items
  comparison           – side-by-side vs competitor / previous version / size chart
  platform_crop        – composition designed for a specific placement (square/9:16/banner)

BEST SELLERS – EMOTIONAL:
  bs_emotional_using   – candid/semi-candid of people genuinely enjoying the product
  bs_explaining        – person explaining or demonstrating the product
  bs_ecosystem         – product alongside the customer's daily items (ecosystem shot)
  bs_emotional_appeal  – imagery that triggers feeling before function

BEST SELLERS – UTILITY & AUDIENCE:
  bs_real_life         – product solving a problem in an everyday realistic context
  bs_segments          – same product used by visibly different customer segments

BEST SELLERS – DECISION:
  bs_price_feature     – callout for price badge, key feature, colour, or spec
  bs_emotion_decision  – the moment of desire just before buying
  bs_envision          – viewer imagines their life improved by the product
  bs_skim_vs_buyer     – bold stop-scroll cue for fast scroller + detail for serious buyer
  bs_artistic          – editorial / campaign creative, unconventional angle or mood

USE CASE TEMPLATES:
  virtual_tryon        – AR try-on mockup (apparel / eyewear / furniture)
""".strip()

# ── LLM prompts ──────────────────────────────────────────────────────────────
_SELECTOR_SYSTEM = """
You are an award-winning Creative Director at a global advertising agency with 10+ years
experience producing high-converting ad creatives across ALL platforms and formats — social
media (Facebook, Instagram, TikTok, LinkedIn, Pinterest), Google Display, YouTube thumbnails,
website hero banners, email headers, print, and out-of-home.
Your job is NOT to produce a beautiful AI image — it is to produce an ADVERTISEMENT that converts.

Before writing anything, derive the campaign intent from the brief:
- Who is the audience? What problem are they living with?
- What action must they take? What emotion should the creative trigger?
- What is the SINGLE message this image must communicate?

Your job:
1. Select 1–3 image use cases from the catalogue that best fit this specific campaign.
2. Write a single AI image generation prompt describing a COMPLETE, READY-TO-POST ad creative
   where the VISUAL and the TEXT are designed together as one cohesive advertisement.

VISUAL REASONING (critical — THINK, do not template; applies to ANY industry):
- The image is NEVER a pretty background with text on top. The scene itself must communicate
  70–80% of the message BEFORE the viewer reads a word: what is happening, what problem is
  shown, what solution is offered, what action to take.
- THE STRANGER TEST (two questions, BOTH must pass with all text removed):
  a) "What is this ad about?" — a clear CATEGORY CUE from the industry/niche must be visible
     in the frame (e.g. a house somewhere in a home-loan ad — through the window, on the
     documents, keys, the front door; the training space for a gym). Never drop the category
     object — without it the ad reads as generic.
  b) "What is being promised?" — the stranger must also see the PROMISE. The category alone
     is not enough: a house says "property-ish", it does not say "low interest".
- SETTING MUST GROUND THE INDUSTRY (mandatory — this applies to whatever industry is given,
  not a fixed list): put the subject in, or visibly near, a location or object set that
  unmistakably belongs to THIS industry's world. Work it out fresh each time — ask "where
  would this exact moment realistically happen, and what object from that world can sit in
  frame?" A generic location (plain desk, blank laptop, neutral room) with NO industry object
  anywhere is a FAILED prompt even if the emotion and copy are perfect — the viewer must
  recognise the industry from the background alone, before reading any text. If the story
  needs a non-industry location, still insert one bridging industry object into that scene.
- CATEGORY CUE + PROOF TOGETHER: ground the scene with the industry object AND prove the
  message on camera — a difference being compared, a result being revealed, a burden
  shrinking, competitors queuing, a before/after inside one frame.
- BANNED: generic stock-photo scenes with no story (smiling person at laptop, handshake,
  team huddle). Every prop must earn its place in the story.

WHAT A REAL AD CREATIVE MUST CONTAIN (all of these):
- A story-driven photograph that shows the problem, transformation, or outcome
- A prominent PAIN POINT or HOOK as a SHORT billboard line (max 6 words) — 3-second scroll-stop
- A SHORT HEADLINE punch (max 8 words) — industry/ICP specific, NOT a long feed sentence
- A CTA element visible on the image (button, badge, or call-to-action text)
- Clean professional layout with clear visual hierarchy for the chosen platform
- Human subjects: sharp, clear, fully visible faces with real emotion — NOT catalogue smiles

EXPRESSION DIRECTION (critical — direct every face like a film director):
- For EACH person, spell out the exact facial expression AND body language matched to their
  role in the story. Image models default to happy smiles, which kills the story.
- PROBLEM/BEFORE state: visibly negative and specific — self-conscious closed lips, worried
  brow, hand covering the mouth in embarrassment (NOT laughing behind the hand), tense
  posture, eyes lowered or avoiding camera.
- SOLUTION/AFTER state: the opposite — open confident smile, relaxed posture, direct gaze.
- Before/after in one frame: the two expressions must be clear OPPOSITES; state explicitly
  that the "before" person is NOT smiling and looks troubled.
- Write micro-direction ("eyebrows pulled together", "shy sideways glance", "exhale of
  relief") so the emotion cannot be misread.

ON-IMAGE TEXT (critical):
- Text reinforces the remaining 20–30% of the message — it must match what the scene shows.
- Burn ONLY short billboard lines. Never put long Facebook primary text / hook essays on the photo.
- Prefer industry vocabulary that the ICP recognises in under 3 seconds.

PLATFORM-AWARE LAYOUT RULES:
- Social feed (Instagram/Facebook/TikTok/LinkedIn): text in upper or lower third, bold
- Website hero / banner: wide landscape, full-bleed scene, centred headline
- Google Display: clean minimal background, high contrast text, prominent CTA
- Print / OOH: high resolution, strong contrast, single dominant message
- Stories / Reels (9:16): vertical full-bleed, text near centre, large CTA

CRITICAL — VARIATION RULES:
- Every generation MUST use a DIFFERENT scene, person, setting, angle, and colour tone.
- The "creative_angle" in the user message MUST drive the background photograph.
- Rotate through diverse real-life contexts relevant to the industry and audience.

Output ONLY valid JSON — no markdown, no explanation outside the JSON:
{
  "use_cases": ["id1", "id2"],
  "prompt": "full ad creative image prompt here",
  "reasoning": "one sentence on why these use cases and layout fit this specific campaign"
}

PROMPT STRUCTURE (follow this order in one paragraph):
1. Visual story FIRST: ONE continuous scene that SHOWS the single message — subject, action,
   story props and visible stakes, emotion on faces, environment, lighting, camera angle, depth of field
2. Pain point / hook text: exact wording; upper-center placement, font style, colour
3. Headline text: exact wording, bold and prominent, position below hook
4. Optional subtext line below headline (small, readable)
5. CTA element: button or badge with exact text, colour, position in lower third
6. Composition, colour palette, overall mood appropriate for the platform
7. CRITICAL QUALITY: single full-bleed photo only — NO mirrored left/right panels, NO blurred
   vertical strips, NO stretched halves, NO collage or split layouts. Do NOT leave empty white
   space at the top for a logo (brand logo is composited in a separate white strip in post).
8. NO additional logos, watermarks, or text beyond what is described above

Prompt length: 120–260 words, one continuous paragraph.
""".strip()

# Creative angles rotated to force variation on each call
_CREATIVE_ANGLES = [
    "golden-hour outdoor lifestyle scene with warm backlight",
    "clean minimal studio shot with white background and dramatic side lighting",
    "candid indoor scene in a modern home or office, soft window light",
    "overhead flat-lay on a textured surface, cool neutral tones",
    "close-up macro detail shot, shallow depth of field, bokeh background",
    "person in action using the product, dynamic low angle, vibrant energy",
    "moody evening scene, rich dark tones, product as hero with accent lighting",
    "bright airy outdoor cafe or workspace setting, natural daylight",
    "professional workspace scene with person, clean desk, warm morning light",
    "product surrounded by complementary lifestyle items, editorial styling",
    "split-light portrait with person and product, half studio half natural",
    "expansive wide shot with person small in frame, environment as context",
]

_SELECTOR_FALLBACK_USE_CASES: list[str] = ["hero_product", "lifestyle"]

# ────────────────────────────────────────────────────────────────────────────


class ImagePlan:
    """Result of the intelligent image planning step."""
    __slots__ = ("use_cases", "prompt", "reasoning")

    def __init__(self, use_cases: list[str], prompt: str, reasoning: str = "") -> None:
        self.use_cases = use_cases
        self.prompt = prompt
        self.reasoning = reasoning

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_cases": self.use_cases,
            "prompt": self.prompt,
            "reasoning": self.reasoning,
        }


def _build_campaign_summary(
    brief: dict[str, Any],
    brand: dict[str, Any],
    copy: dict[str, Any] | None = None,
) -> str:
    """Compact campaign context block sent to the LLM selector."""
    lines = [
        f"BRAND: {brand.get('brand_name') or brief.get('brand_name', 'Unknown')}",
        f"BRAND PRIMARY COLOUR: {brand.get('primary_color', '#0F1B3D')}",
        f"BRAND SECONDARY COLOUR: {brand.get('secondary_color', '#00C2A8')}",
        f"INDUSTRY: {brief.get('target_industry_label') or brand.get('agency_industry', '')}",
        f"PRODUCT / SERVICE: {brief.get('campaign_product') or brief.get('product_name', '')}",
        f"KEY OFFER: {(brief.get('key_benefits') or {}).get('offer') or brief.get('notes', '')}",
        f"TARGET AUDIENCE: {brief.get('audience') or brief.get('audience_type', '')}",
        f"TONE: {brief.get('ad_copy_tone', '')}",
        f"OBJECTIVE: {brief.get('objective_id', '')}",
        f"PLATFORM / FORMAT: {brief.get('formats') or brief.get('placements') or 'general digital ad'}",
        f"ASPECT RATIO: {brief.get('image_aspect_ratio', '1:1')}",
        f"CTA TEXT: {brief.get('cta_text') or brief.get('cta', 'Learn More')}",
    ]
    # ── If actual generated copy is available, include it directly ────────────
    if copy:
        hook = (copy.get("hook") or "").strip()
        headline = (copy.get("headline") or "").strip()
        body = (copy.get("body_copy") or "").strip()
        cta = (copy.get("cta") or "").strip()
        if hook:
            lines.append(f"PAIN POINT / HOOK TEXT (must appear large on image): \"{hook}\"")
        if headline:
            lines.append(f"HEADLINE TEXT (bold, prominent): \"{headline}\"")
        if body:
            lines.append(f"BODY / SUBTEXT (smaller, below headline): \"{body[:120]}\"")
        if cta:
            lines.append(f"CTA BUTTON TEXT (on coloured button): \"{cta}\"")
    # ── Use-case hints ────────────────────────────────────────────────────────
    manual = brief.get("image_use_cases") or []
    if manual:
        lines.append(f"PREFERRED USE CASES (treat as strong hints): {', '.join(manual)}")
    user_prompt = (brief.get("image_prompt_override") or "").strip()
    if user_prompt:
        lines.append(f"USER CUSTOM DIRECTION (incorporate): {user_prompt[:400]}")
    return "\n".join(l for l in lines if l.split(": ", 1)[-1].strip())


def _parse_llm_plan(raw: str) -> dict[str, Any] | None:
    """Extract JSON from LLM output, handling markdown fences."""
    text = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    try:
        data = json.loads(text)
        if isinstance(data.get("use_cases"), list) and isinstance(data.get("prompt"), str):
            return data
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


def _mock_plan(brief: dict[str, Any], brand: dict[str, Any]) -> ImagePlan:
    product = brief.get("campaign_product") or brief.get("product_name") or brand.get("brand_name") or "the product"
    ratio = brief.get("image_aspect_ratio", "1:1")
    prompt = _mock_prompt(product, "lifestyle", ratio)
    return ImagePlan(
        use_cases=["hero_product", "lifestyle"],
        prompt=prompt,
        reasoning="Default plan used (no API key). Add OPENROUTER_API_KEY for intelligent selection.",
    )


def _get_openrouter_client() -> Any:
    import openai
    headers: dict[str, str] = {"X-Title": settings.APP_NAME}
    referer = settings.openrouter_http_referer
    if referer:
        headers["HTTP-Referer"] = referer
    return openai.OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        default_headers=headers,
    )


async def select_and_build_image_plan(
    brief: dict[str, Any],
    brand: dict[str, Any],
    copy: dict[str, Any] | None = None,
) -> ImagePlan:
    """
    Core intelligent pipeline:
    1. LLM reads campaign context + generated ad copy (hook, headline, CTA).
    2. Selects best 1-3 use cases.
    3. Writes a complete Meta ad image prompt — background photo + ad text layout.
    Returns ImagePlan(use_cases, prompt, reasoning).
    """
    if not settings.OPENROUTER_API_KEY:
        return _mock_plan(brief, brand)

    campaign_summary = _build_campaign_summary(brief, brand, copy=copy)
    creative_angle = random.choice(_CREATIVE_ANGLES)
    has_copy = bool(copy and (copy.get("hook") or copy.get("headline")))
    user_msg = (
        f"{_USE_CASE_CATALOGUE}\n\n"
        f"---\n"
        f"CAMPAIGN DETAILS:\n{campaign_summary}\n\n"
        f"REQUIRED BACKGROUND CREATIVE ANGLE: {creative_angle}\n"
        f"(The background photograph MUST be based on this angle — avoid generic desk/laptop scenes)\n\n"
        + (
            "IMPORTANT: Use ONLY the short hook/headline/CTA lines above as on-image text.\n"
            "They must appear exactly — large billboard style. Do NOT expand them into long sentences.\n"
            "Describe placement, font weight, colour, and size in the prompt.\n\n"
            if has_copy else
            "Note: Ad copy will be generated separately. Focus on a compelling visual layout\n"
            "with placeholder SHORT text positions (hook area max 6 words, headline max 8 words, CTA button).\n\n"
        )
        + "Write the use cases and the complete ad creative image prompt now. "
        + "Ensure the layout, text size, and composition match the PLATFORM / FORMAT listed above."
    )

    try:
        client = _get_openrouter_client()
        model = settings.OPENROUTER_MODEL_CLAUDE or "anthropic/claude-haiku-4.5"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SELECTOR_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=700,
            temperature=0.95,
        )
        raw = (response.choices[0].message.content or "").strip()
        data = _parse_llm_plan(raw)

        if data:
            # Keep long prompts available in the UI; downstream providers can still sanitize as needed.
            prompt = (data.get("prompt") or "").strip()
            if len(prompt) > 4000:
                prompt = prompt[:3999] + "…"
            use_cases = [
                uc for uc in (data.get("use_cases") or [])
                if uc in _USE_CASE_DESCRIPTIONS
            ] or _SELECTOR_FALLBACK_USE_CASES
            return ImagePlan(
                use_cases=use_cases,
                prompt=prompt,
                reasoning=(data.get("reasoning") or "").strip(),
            )

        # LLM returned non-JSON — try to salvage the text as the prompt
        logger.warning("LLM did not return valid JSON for image plan; using text as prompt")
        prompt = raw[:950] if raw else _mock_plan(brief, brand).prompt
        return ImagePlan(
            use_cases=_SELECTOR_FALLBACK_USE_CASES,
            prompt=prompt,
            reasoning="Use cases auto-selected (LLM returned plain text).",
        )

    except Exception:
        logger.exception("select_and_build_image_plan failed")
        return _mock_plan(brief, brand)

_SYSTEM_PROMPT = """
You are a world-class AI image prompt engineer specialising in commercial advertising photography.
Your output is a single, richly detailed image generation prompt (for tools like Midjourney,
DALL-E, Stable Diffusion, Flux, or Firefly).

Rules:
- Write ONE continuous prompt paragraph — no bullet points, no headers.
- Include: subject/product, action or pose, scene/environment, lighting quality & direction,
  colour palette, mood/atmosphere, camera angle, lens characteristics (shallow DoF, wide etc.),
  and any stylistic references.
- Any human subjects: sharp, clear, fully visible faces — NOT blurred, obscured, or turned away.
- Do NOT include on-screen text, logos, watermarks, or captions inside the image.
- Do NOT write a video script, talking points, or marketing copy.
- Keep the output between 80 and 250 words.
- Respond with ONLY the prompt text — no preamble, no labels.
""".strip()

_REFINE_SYSTEM_PROMPT = """
You are a world-class AI image prompt engineer.
The user has written a base prompt. Enrich it with the requested use case context while keeping
the user's core scene description intact. Output ONLY the improved prompt — no preamble, no labels.
Keep human faces sharp and clear. No on-screen text or logos inside the image.
""".strip()


def _build_user_message(
    *,
    product_name: str,
    brand_name: str,
    offer: str,
    target_audience: str,
    ad_copy_tone: str,
    image_use_cases: list[str],
    image_aspect_ratio: str,
    forbidden_words: list[str],
    user_prompt: str = "",
) -> str:
    use_case_descs = [
        _USE_CASE_DESCRIPTIONS.get(uc, uc)
        for uc in image_use_cases
        if uc
    ]
    ratio_hint = _RATIO_HINTS.get(image_aspect_ratio, f"aspect ratio {image_aspect_ratio}")
    forbidden = ", ".join(forbidden_words) if forbidden_words else "none"

    if user_prompt:
        # User already wrote a prompt — enrich it with use case context
        parts = [
            f"USER'S BASE PROMPT: {user_prompt}",
            "",
            f"ENRICH WITH USE CASE CONTEXT: {'; '.join(use_case_descs) if use_case_descs else 'general product image'}",
            f"PRODUCT / BRAND: {product_name or brand_name or 'the product'}",
            f"CANVAS / ASPECT RATIO: {ratio_hint}",
            f"FORBIDDEN ELEMENTS: {forbidden}",
            "",
            "Improve and enrich the base prompt while keeping the user's scene description as the primary source of truth.",
        ]
    else:
        parts = [
            f"PRODUCT / BRAND: {product_name or brand_name or 'the product'}",
            f"KEY MESSAGE / OFFER: {offer or 'highlight the product quality'}",
            f"TARGET AUDIENCE: {target_audience or 'general consumer'}",
            f"TONE: {ad_copy_tone or 'premium, aspirational'}",
            f"IMAGE USE CASES: {'; '.join(use_case_descs) if use_case_descs else 'general product image'}",
            f"CANVAS / ASPECT RATIO: {ratio_hint}",
            f"FORBIDDEN ELEMENTS: {forbidden}",
            "",
            "Write a detailed AI image generation prompt that captures ALL the listed use cases in a single cohesive scene.",
        ]
    return "\n".join(parts)


def _mock_prompt(product_name: str, use_case: str, ratio: str) -> str:
    desc = _USE_CASE_DESCRIPTIONS.get(use_case, "product image")
    return (
        f"Professional commercial photograph: {desc} of {product_name or 'the product'}, "
        f"soft natural lighting, shallow depth of field, muted warm colour palette, "
        f"clean minimalist background, {ratio} composition, 8K photorealistic detail, "
        "no text overlays."
    )


async def generate_image_prompt(data: object) -> str:
    """Return a detailed AI image generation prompt string."""
    product_name: str = getattr(data, "product_name", "") or ""
    brand_name: str = getattr(data, "brand_name", "") or ""
    offer: str = getattr(data, "offer", "") or ""
    target_audience: str = getattr(data, "target_audience", "") or ""
    ad_copy_tone: str = getattr(data, "ad_copy_tone", "") or ""
    # Support both old single and new multi-select
    image_use_case_single: str = getattr(data, "image_use_case", "") or ""
    image_use_cases_list: list[str] = list(getattr(data, "image_use_cases", None) or [])
    if image_use_case_single and image_use_case_single not in image_use_cases_list:
        image_use_cases_list = [image_use_case_single] + image_use_cases_list
    image_aspect_ratio: str = getattr(data, "image_aspect_ratio", "1:1") or "1:1"
    forbidden_words: list[str] = list(getattr(data, "forbidden_words", None) or [])
    user_prompt: str = getattr(data, "user_prompt", "") or ""

    if not settings.OPENROUTER_API_KEY:
        first_uc = image_use_cases_list[0] if image_use_cases_list else ""
        return _mock_prompt(product_name or brand_name, first_uc, image_aspect_ratio)

    try:
        import openai

        headers = {"X-Title": settings.APP_NAME}
        referer = settings.openrouter_http_referer
        if referer:
            headers["HTTP-Referer"] = referer

        client = openai.OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            default_headers=headers,
        )

        system = _REFINE_SYSTEM_PROMPT if user_prompt else _SYSTEM_PROMPT
        user_msg = _build_user_message(
            product_name=product_name,
            brand_name=brand_name,
            offer=offer,
            target_audience=target_audience,
            ad_copy_tone=ad_copy_tone,
            image_use_cases=image_use_cases_list,
            image_aspect_ratio=image_aspect_ratio,
            forbidden_words=forbidden_words,
            user_prompt=user_prompt,
        )

        model = settings.OPENROUTER_MODEL_CLAUDE or "anthropic/claude-haiku-4.5"
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=500,
        )
        text = (response.choices[0].message.content or "").strip()
        first_uc = image_use_cases_list[0] if image_use_cases_list else ""
        return text or _mock_prompt(product_name or brand_name, first_uc, image_aspect_ratio)

    except Exception:
        logger.exception("Image prompt generation failed")
        first_uc = image_use_cases_list[0] if image_use_cases_list else ""
        return _mock_prompt(product_name or brand_name, first_uc, image_aspect_ratio)
