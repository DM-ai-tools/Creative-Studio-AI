"""Creative Studio Supercomputer chat — image (GPT Image 2) then Seedance video."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings
from app.services.prompt_llm_catalog import (
    default_prompt_llm_model,
    resolve_prompt_llm_model,
)

logger = logging.getLogger(__name__)

SEEDANCE_VIDEO_MODEL = "ark-seedance-2-0"
DEFAULT_IMAGE_MODEL = "openai-gpt-image-2"

# Explicit UI / client actions (approve-before-video, like Higgsfield Supercomputer)
ACTIONS = frozenset(
    {
        "continue",
        "generate_image",
        "regenerate_image",
        "approve_next",
        "generate_video",
        "generate_storyboard",
    }
)

_SYSTEM = """You are Creative Studio — a production agent (think Higgsfield Supercomputer / ChatGPT agent mode).

Read the USER'S FULL BRIEF carefully. If they wrote Scene 1 / Scene 2 / … (or CLIP beats), that is a STORYBOARD — do NOT collapse it into one still.

Pipeline:
1) draft_plan — extract scenes + still prompts + full motion prompt
2) generate_image / generate_storyboard — GPT Image 2: ONE still per scene (Higgsfield-style board)
3) User reviews board → Approve & Next → Seedance 2.0 video for the FULL multi-scene story

Respond with ONLY valid JSON (no markdown fences):
{
  "assistant_message": "short reply; say how many scenes you found + next step",
  "intent": "reply" | "draft_plan" | "generate_image" | "generate_video",
  "image_prompt": "Scene 1 / opening still only",
  "video_prompt": "FULL timed multi-scene Seedance prompt covering EVERY scene + overlays",
  "scenes": [
    {"title": "Hook", "image_prompt": "visual still for this scene only — NO on-image text", "overlays": ["optional overlay copy"]}
  ],
  "duration_seconds": integer 5-120 (or null when Auto/script-derived),
  "aspect": "9/16" | "1/1" | "16/9" | "4/3",
  "suggested_actions": ["generate_image"]
}

CRITICAL:
- Multi-scene briefs → fill "scenes" array (one entry per Scene). image_prompt = Scene 1 only.
- Each scene image_prompt = that scene's keyframe ONLY (do not mash Scene 1 + product reveal into one frame).
- NO burned-in text in image prompts (overlays go in scenes[].overlays and video_prompt).
- video_prompt must include every scene as timed CLIP beats + overlay lines.
- Product photo attachments = PRODUCT LOCK for product scenes only.
- Auto/Generate: draft_plan then system will auto-start storyboard generation.
- Ask: intent=reply only.
"""


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_aspect(value: str | None, fallback: str) -> str:
    raw = (value or fallback or "9/16").replace(":", "/").strip()
    allowed = {"9/16", "1/1", "16/9", "4/3", "1/4"}
    return raw if raw in allowed else "9/16"


def _explicit_duration_from_text(text: str) -> int | None:
    """Honor a duration written by the user before applying Auto estimation."""
    raw = text or ""
    seconds = re.search(
        r"(?i)\b(\d{1,3})\s*[- ]?\s*(?:seconds?|secs?)\b",
        raw,
    )
    if seconds:
        return max(5, min(120, int(seconds.group(1))))
    minutes = re.search(
        r"(?i)\b(\d{1,2})\s*[- ]?\s*(?:minutes?|mins?)\b",
        raw,
    )
    if minutes:
        return max(5, min(120, int(minutes.group(1)) * 60))
    return None


def _estimate_script_duration(text: str) -> int:
    """Choose a useful runtime from the brief when the user selects Auto."""
    raw = re.sub(r"\s+", " ", text or "").strip()
    if not raw:
        return 15
    explicit = _explicit_duration_from_text(raw)
    if explicit is not None:
        return explicit
    scene_count = len(re.findall(r"(?i)\b(?:scene|clip)\s*\d+\b", raw))
    if scene_count >= 2:
        # Scene briefs describe shots, overlays, and production notes—not spoken
        # narration. Allocate cinematic screen time per scene instead of charging
        # one second for every written word.
        per_scene = 7
        if re.search(r"(?i)\b(?:rapid|multiple|four|four rapid)\b.*\b(?:cuts?|shots?)\b", raw):
            per_scene += 2
        if re.search(r"(?i)\b(?:hold steady|final hero|ending|cta)\b", raw):
            per_scene += 1
        # Auto may suggest a useful runtime, but expensive long-form generation
        # requires the user to explicitly request the duration.
        return max(15, min(60, int(round(scene_count * per_scene / 5) * 5)))
    # Spoken/visual script pacing: roughly 2.5 words per second, with enough
    # time for a cinematic opening, product coverage and a deliberate ending.
    words = len(re.findall(r"\b[\w'-]+\b", raw))
    estimated = max(15, round(words / 2.5))
    return max(5, min(60, int(round(estimated / 5) * 5)))


def _normalize_duration(value: Any, fallback: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = int(fallback or 10)
    if n <= 5:
        return 5
    return min(120, n)


def _motion_prompt_is_weak(prompt: str) -> bool:
    text = (prompt or "").strip()
    if len(text) < 180:
        return True
    low = text.lower()
    weak_only = (
        "animate this exact scene",
        "animate this scene",
        "animate the still",
        "continuous natural motion",
        "camera slowly",
        "gentle camera",
    )
    has_beats = bool(
        re.search(r"(?i)\bCLIP\s*[123]\b|\bHOOK\b|\bBODY\b|\b0\s*[–\-]\s*\d+\s*s", text)
    )
    if has_beats:
        return False
    if any(w in low for w in weak_only) and len(text) < 600:
        return True
    return len(text) < 280


def _heuristic_timed_motion(
    *,
    user_brief: str,
    image_prompt: str,
    video_prompt: str,
    duration_seconds: int,
    sound_on: bool,
) -> str:
    """Expand a thin motion line into timed Seedance beats from the full brief."""
    from app.services.creative_studio_prompt_service import _clip_windows

    brief = (user_brief or video_prompt or image_prompt or "").strip()
    still = (image_prompt or "").strip()
    secs = _normalize_duration(duration_seconds, 10)
    windows = _clip_windows(secs)
    chunks = re.split(r"(?i)\b(?:then|next|after that|finally|,\s*and\s+then)\b|[.;]\s+", brief)
    chunks = [re.sub(r"\s+", " ", c).strip(" -") for c in chunks if len(c.strip()) > 12]
    if not chunks:
        chunks = [brief[:400] or still[:400] or "Subject performs the described action"]

    while len(chunks) < len(windows):
        chunks.append(chunks[-1])
    clips: list[str] = []
    for i, (a, b) in enumerate(windows):
        # Partition all instructions across the windows; the old first-three-only
        # fallback silently lost the closing action and CTA in longer briefs.
        first = i * len(chunks) // len(windows)
        last = (i + 1) * len(chunks) // len(windows)
        beat = ". ".join(chunks[first:last])
        if i == 0 and still:
            beat = (
                f"Start locked to the approved opening still, then immediately move: {beat}. "
                f"Still reference: {still[:280]}"
            )
        clips.append(f"CLIP {i + 1} — {a}–{b} SECONDS: {beat}")

    audio = (
        "AUDIO: Native diegetic sound on — ambient environment, realistic foley "
        "(hands, latch, footsteps, animals, fabric), optional short natural speech matching the scene. "
        "Do not stay silent."
        if sound_on
        else "AUDIO: Silent video — no speech, no music, no voiceover."
    )
    return (
        f"{secs}-SECOND CONTINUOUS STORY — follow EVERY beat below (do not freeze on the first frame).\n\n"
        + "\n\n".join(clips)
        + f"\n\nContinuity: same subject, wardrobe, location, and lighting across all beats.\n"
        f"Camera: motivated handheld / gimbal moves; actions must progress beat by beat.\n"
        f"{audio}\n"
        f"STRICT: no on-screen text, captions, logos, or watermarks."
    )


async def _ensure_rich_motion_prompt(
    *,
    model_slug: str,
    user_brief: str,
    image_prompt: str,
    video_prompt: str,
    duration_seconds: int,
    sound_on: bool,
    brand_name: str,
    product_name: str,
) -> str:
    """Guarantee Seedance gets a full timed story, not a one-liner pan on the still."""
    motion = (video_prompt or "").strip()
    if not _motion_prompt_is_weak(motion):
        # Still append audio line if missing when sound requested
        if sound_on and not re.search(r"(?i)\baudio\b|\bsound\b|\bfoley\b|\bspeech\b", motion):
            motion = (
                f"{motion}\n\nAUDIO: Native diegetic sound — ambient + foley; "
                "short natural dialogue only if it fits. Not silent."
            )
        return motion

    import asyncio

    from app.services.image_prompt_service import _get_openrouter_client

    fallback = _heuristic_timed_motion(
        user_brief=user_brief,
        image_prompt=image_prompt,
        video_prompt=video_prompt,
        duration_seconds=duration_seconds,
        sound_on=sound_on,
    )
    if not settings.OPENROUTER_API_KEY:
        return fallback

    expand_system = (
        "Expand the user's creative brief into ONE Seedance 2.0 VIDEO prompt. "
        "Output ONLY the prompt text (no JSON, no markdown). "
        f"Duration MUST be exactly {duration_seconds} seconds with enough timed beats "
        "to cover the complete story. "
        "The approved still is ONLY the opening frame — the video MUST progress through every "
        "action in the brief (not a frozen still with a slight pan). "
        "Include camera, hands, product, environment continuity. "
        + (
            "Include AUDIO: diegetic ambient + foley; optional short natural speech."
            if sound_on
            else "End with AUDIO: silent — no speech/music."
        )
        + " Preserve every requested action and narration line. Max 12000 characters."
    )
    user_msg = (
        f"Brand: {brand_name or '—'}\nProduct: {product_name or '—'}\n"
        f"Duration: {duration_seconds}s\nSound: {'on' if sound_on else 'off'}\n\n"
        f"USER BRIEF:\n{user_brief or ''}\n\n"
        f"OPENING STILL PROMPT:\n{(image_prompt or '')[:1200]}\n\n"
        f"CURRENT (WEAK) VIDEO PROMPT:\n{(video_prompt or '')[:1200]}\n\n"
        "Write the full timed Seedance prompt now."
    )
    try:
        client = _get_openrouter_client()
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=model_slug,
                temperature=0.35,
                max_tokens=4000,
                messages=[
                    {"role": "system", "content": expand_system},
                    {"role": "user", "content": user_msg},
                ],
            )
        )
        raw = (completion.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", raw).strip()
        if len(raw) >= 180:
            return raw
    except Exception as exc:
        logger.warning("Motion prompt expand failed, using heuristic: %s", exc)
    return fallback


def _default_image_model() -> str:
    from app.services.media.openai_image_catalog import openai_configured

    if openai_configured():
        return DEFAULT_IMAGE_MODEL
    from app.services.media.higgsfield_models import higgsfield_configured

    if higgsfield_configured():
        return "hf-text2image-soul-v2"
    return DEFAULT_IMAGE_MODEL


async def _llm_plan(
    *,
    model_slug: str,
    mode_norm: str,
    duration_seconds: int,
    aspect: str,
    sound_on: bool,
    brand_name: str,
    product_name: str,
    attachments: list[str],
    messages: list[dict[str, Any]],
    phase: str,
    image_prompt: str,
    video_prompt: str,
    approved_image_url: str,
    revision_notes: str,
) -> dict[str, Any]:
    import asyncio

    from app.services.image_prompt_service import _get_openrouter_client

    history_lines: list[str] = []
    for m in messages[-16:]:
        role = str(m.get("role") or "user")
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        history_lines.append(f"{role.upper()}: {content}")

    context_bits = [
        f"Mode: {mode_norm}",
        f"Pipeline phase: {phase or 'idle'}",
        f"Preferred duration_seconds: {duration_seconds}",
        f"Preferred aspect: {aspect}",
        f"Sound on: {sound_on}",
        f"Brand: {brand_name or '—'}",
        f"Product: {product_name or '—'}",
        f"Attachments (product photos to match): {', '.join(attachments) if attachments else 'none'}",
        f"Current image_prompt: {(image_prompt or '—')[:800]}",
        f"Current video_prompt: {(video_prompt or '—')[:800]}",
        f"Approved still URL: {approved_image_url or 'none'}",
        f"Revision notes: {revision_notes or 'none'}",
        "Image model: GPT Image 2 (openai-gpt-image-2).",
        "Video model: Seedance 2.0 (ark-seedance-2-0).",
        "IMPORTANT: video_prompt must cover the FULL brief with timed CLIP beats — "
        "never only 'animate this still'. image_prompt is opening frame only.",
        "If attachments are present, the still MUST match that product photo exactly.",
    ]

    user_payload = (
        "CONTEXT:\n"
        + "\n".join(f"- {b}" for b in context_bits)
        + "\n\nCONVERSATION:\n"
        + ("\n".join(history_lines) or "(empty)")
        + "\n\nRespond with the JSON object now."
    )

    if not settings.OPENROUTER_API_KEY:
        # Offline fallback: draft from last user message
        last_user = ""
        for m in reversed(messages):
            if str(m.get("role") or "") == "user" and str(m.get("content") or "").strip():
                last_user = str(m.get("content") or "").strip()
                break
        return {
            "assistant_message": (
                "OpenRouter chat isn’t configured — drafted still + timed motion beats from your message. "
                "Click Generate image when ready."
            ),
            "intent": "draft_plan",
            "image_prompt": last_user[:2000],
            "video_prompt": _heuristic_timed_motion(
                user_brief=last_user,
                image_prompt=last_user,
                video_prompt="",
                duration_seconds=duration_seconds,
                sound_on=sound_on,
            ),
            "duration_seconds": duration_seconds,
            "aspect": aspect,
            "suggested_actions": ["generate_image"],
        }

    try:
        client = _get_openrouter_client()
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=model_slug,
                temperature=0.4,
                max_tokens=6000,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_payload},
                ],
            )
        )
        raw = (completion.choices[0].message.content or "").strip()
        return _extract_json(raw) or {}
    except Exception as exc:
        logger.exception("Creative Studio chat LLM failed: %s", exc)
        return {
            "assistant_message": (
                "I hit an issue contacting the chat model. Try again or switch chat model."
            ),
            "intent": "reply",
            "suggested_actions": [],
        }


async def _start_job(
    *,
    tenant_id: str,
    media_mode: str,
    model: str,
    prompt: str,
    duration_seconds: int,
    aspect: str,
    resolution: str,
    sound_on: bool,
    seed_image_url: str | None,
    seed_image_role: str = "first_frame",
    product_name: str = "",
    brand_name: str = "",
    product_reference_url: str | None = None,
    logo_reference_url: str | None = None,
    additional_reference_urls: list[str] | None = None,
    reference_assets: list[dict[str, str]] | None = None,
    source_brief: str = "",
    storyboard_scenes: list[dict[str, Any]] | None = None,
    storyboard_image_urls: list[str] | None = None,
) -> str:
    import asyncio

    from app.services.creative_studio_job_service import (
        create_job,
        run_creative_studio_job,
    )

    job_id = await create_job(
        tenant_id=tenant_id,
        payload={
            "media_mode": media_mode,
            "model": model,
            "prompt": prompt,
            "duration_seconds": duration_seconds,
            "aspect": aspect,
            "resolution": resolution or "1080p",
            "sound_on": bool(sound_on) if media_mode == "video" else False,
            "product_name": product_name or "",
            "brand_name": brand_name or "",
            # Video overlays are intentional campaign copy; do not globally ban text.
            "negative_prompt": "watermark, random unreadable text, UI chrome",
            "seed_image_url": seed_image_url,
            "seed_image_role": seed_image_role or "first_frame",
            "product_reference_url": product_reference_url,
            "logo_reference_url": logo_reference_url,
            "additional_reference_urls": additional_reference_urls or [],
            "reference_assets": reference_assets or [],
            "source_brief": source_brief,
            "storyboard_scenes": storyboard_scenes or [],
            "storyboard_image_urls": storyboard_image_urls or [],
        },
    )
    asyncio.create_task(run_creative_studio_job(job_id))
    return job_id


def _find_full_user_brief(messages: list[dict[str, Any]], last_user: str) -> str:
    """Prefer the longest creative brief in chat (not Approve / Generate button labels)."""
    best = (last_user or "").strip()
    for m in messages:
        if str(m.get("role") or "") != "user":
            continue
        content = str(m.get("content") or "").strip()
        low = content.lower()
        if low.startswith("approve") or low.startswith("generate image") or low.startswith("regenerate"):
            continue
        if len(content) > len(best):
            best = content
    return best


def _scenes_from_llm_or_brief(
    parsed_scenes: Any,
    brief: str,
    *,
    product_name: str,
) -> list[dict[str, Any]]:
    from app.services.creative_studio_storyboard import (
        looks_like_multi_scene_brief,
        parse_storyboard_scenes,
        scene_wants_product,
    )

    # Prefer deterministic Scene 1/2/… parse from the user brief (avoids product bleed)
    if looks_like_multi_scene_brief(brief):
        parsed = parse_storyboard_scenes(brief, product_name=product_name)
        if len(parsed) >= 2:
            return parsed

    out: list[dict[str, Any]] = []
    if isinstance(parsed_scenes, list):
        for i, s in enumerate(parsed_scenes[:40]):
            if not isinstance(s, dict):
                continue
            title = str(s.get("title") or f"Scene {i + 1}").strip()
            ip = str(s.get("image_prompt") or s.get("prompt") or "").strip()
            if not ip:
                continue
            overlays = s.get("overlays") or []
            if not isinstance(overlays, list):
                overlays = []
            idx = i + 1
            wants = scene_wants_product(title=title, visual=ip, index=idx)
            label = product_name or "the product"
            if wants and not re.search(r"(?i)match the attached|product photo", ip):
                ip = (
                    f"{ip} Show {label} matching the attached product photo exactly."
                )
            if not wants and not re.search(
                r"(?i)do NOT show|problem state|wooden chicken coop", ip
            ):
                ip = (
                    f"{ip} Do NOT show {label} in this explicit problem beat. "
                    "Follow the brief's setting and objects."
                )
            out.append(
                {
                    "id": f"scene-{idx}",
                    "index": idx,
                    "title": title[:80],
                    "image_prompt": ip[:2200],
                    "overlays": [str(o)[:120] for o in overlays[:6]],
                    "wants_product": wants,
                }
            )
    if len(out) >= 2:
        return out
    return parse_storyboard_scenes(brief, product_name=product_name)


def _with_product_fidelity(prompt: str, product_ref: str | None) -> str:
    text = (prompt or "").strip()
    if not product_ref:
        return text
    if re.search(r"(?i)product (fidelity|reference)|match the attached product", text):
        return text
    return (
        f"{text}\n\nPRODUCT FIDELITY: Match the attached product photo exactly "
        f"(shape, colour, materials, proportions, branding). Same product — do not invent another."
    )


async def run_creative_studio_chat_turn(
    *,
    tenant_id: str,
    messages: list[dict[str, Any]],
    mode: str = "auto",
    chat_model: str | None = None,
    duration_seconds: int | None = None,
    aspect: str = "9/16",
    resolution: str = "1080p",
    sound_on: bool = True,
    attachment_urls: list[str] | None = None,
    brand_name: str = "",
    product_name: str = "",
    action: str = "continue",
    image_prompt: str = "",
    video_prompt: str = "",
    approved_image_url: str = "",
    image_model: str = "",
    revision_notes: str = "",
    phase: str = "",
    product_reference_url: str = "",
    logo_reference_url: str = "",
    additional_reference_urls: list[str] | None = None,
    reference_assets: list[dict[str, str]] | None = None,
    storyboard_image_urls: list[str] | None = None,
) -> dict[str, Any]:
    """
    Supercomputer turn:
    draft → GPT Image 2 still (optional product photo ref) → approve → Seedance video.
    """
    from app.services.media.byteplus_seedance_client import ark_configured
    from app.services.media.higgsfield_models import higgsfield_configured
    from app.services.media.openai_image_catalog import openai_configured

    mode_norm = (mode or "auto").strip().lower()
    if mode_norm not in {"auto", "ask", "generate"}:
        mode_norm = "auto"

    action_norm = (action or "continue").strip().lower()
    if action_norm not in ACTIONS:
        action_norm = "continue"

    attachments = [u for u in (attachment_urls or []) if (u or "").strip()]
    product_ref = (product_reference_url or "").strip() or (attachments[0] if attachments and not reference_assets else "")
    logo_ref = (logo_reference_url or "").strip()
    extra_refs = [
        u.strip()
        for u in (additional_reference_urls or [])
        if (u or "").strip() and u.strip() not in {product_ref, logo_ref}
    ][:7]
    model_slug = (
        resolve_prompt_llm_model(chat_model)
        if chat_model and chat_model != "auto"
        else default_prompt_llm_model()
    )
    img_model = (image_model or "").strip() or _default_image_model()
    last_user = ""
    for m in reversed(messages):
        if str(m.get("role") or "") == "user" and str(m.get("content") or "").strip():
            last_user = str(m.get("content") or "").strip()
            break
    full_brief = _find_full_user_brief(messages, last_user)
    requested_duration = (
        _normalize_duration(duration_seconds, _estimate_script_duration(full_brief))
        if duration_seconds is not None
        else _estimate_script_duration(full_brief)
    )
    out_duration = requested_duration
    out_aspect = _normalize_aspect(aspect, "9/16")

    # ── Explicit pipeline actions (no LLM required) ──────────────────────────
    if action_norm in {"generate_image", "regenerate_image", "generate_storyboard"}:
        prompt = (image_prompt or "").strip()
        notes = (revision_notes or last_user or "").strip()
        if action_norm == "regenerate_image" and notes:
            # Light refine via LLM when notes provided
            parsed = await _llm_plan(
                model_slug=model_slug,
                mode_norm="generate",
                duration_seconds=out_duration,
                aspect=out_aspect,
                sound_on=sound_on,
                brand_name=brand_name,
                product_name=product_name,
                attachments=attachments,
                messages=messages
                + [
                    {
                        "role": "user",
                        "content": (
                            "Revise the IMAGE prompt only based on these notes, keep video_prompt "
                            f"aligned. Notes: {notes}. Previous image_prompt: {prompt}"
                        ),
                    }
                ],
                phase="revise_image",
                image_prompt=prompt,
                video_prompt=video_prompt,
                approved_image_url=approved_image_url,
                revision_notes=notes,
            )
            prompt = str(parsed.get("image_prompt") or prompt).strip() or prompt
            video_prompt = str(parsed.get("video_prompt") or video_prompt).strip() or video_prompt
            out_aspect = _normalize_aspect(str(parsed.get("aspect") or ""), out_aspect)

        if not prompt:
            prompt = last_user[:2000]
        prompt = _with_product_fidelity(prompt, product_ref or None)
        if not prompt:
            return {
                "assistant_message": "I need an image prompt first — describe the still / background scene.",
                "intent": "reply",
                "phase": "planning",
                "suggested_actions": [],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": SEEDANCE_VIDEO_MODEL,
                "image_prompt": image_prompt or None,
                "video_prompt": video_prompt or None,
                "approved_image_url": approved_image_url or None,
                "product_reference_url": product_ref or None,
                "status": "ok",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
                "error": None,
            }

        if not openai_configured() and not higgsfield_configured():
            return {
                "assistant_message": (
                    "Image generation isn’t configured. Set OPENAI_API_KEY for GPT Image 2 "
                    "(or Higgsfield keys as fallback)."
                ),
                "intent": "reply",
                "phase": "planning",
                "suggested_actions": [],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": SEEDANCE_VIDEO_MODEL,
                "image_prompt": prompt,
                "video_prompt": video_prompt or None,
                "approved_image_url": approved_image_url or None,
                "product_reference_url": product_ref or None,
                "status": "ok",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
                "error": None,
            }

        from app.services.creative_studio_storyboard import (
            build_storyboard_video_prompt,
            looks_like_multi_scene_brief,
            opening_still_prompt,
        )

        brief = full_brief
        scenes = _scenes_from_llm_or_brief(None, brief, product_name=product_name or "product")
        # Also try parsing image_prompt if it embeds Scene markers
        if len(scenes) < 2 and looks_like_multi_scene_brief(prompt):
            scenes = _scenes_from_llm_or_brief(None, prompt, product_name=product_name or "product")

        # Higgsfield-style: multi-scene brief → full storyboard of stills
        if len(scenes) >= 2 and action_norm in {"generate_image", "generate_storyboard", "regenerate_image"}:
            if len(scenes) >= 4 and out_duration < 15:
                out_duration = 15
            vid = (video_prompt or "").strip() or build_storyboard_video_prompt(
                scenes,
                duration_seconds=out_duration,
                sound_on=sound_on,
                product_name=product_name or "",
            )
            img0 = opening_still_prompt(scenes) or prompt
            job_id = await _start_job(
                tenant_id=tenant_id,
                media_mode="storyboard",
                model=img_model,
                prompt=img0,
                duration_seconds=out_duration,
                aspect=out_aspect,
                resolution=resolution,
                sound_on=False,
                seed_image_url=None,
                product_name=product_name,
                brand_name=brand_name,
                product_reference_url=product_ref or None,
                logo_reference_url=logo_ref or None,
                reference_assets=reference_assets,
                storyboard_scenes=scenes,
            )
            titles = ", ".join(str(s.get("title") or f"Scene {i+1}") for i, s in enumerate(scenes[:5]))
            return {
                "assistant_message": (
                    f"Building a {len(scenes)}-scene storyboard like Higgsfield Supercomputer "
                    f"({titles}). Each scene gets its own GPT Image 2 still — product photo locked "
                    "on product beats. When the board is ready, review then Approve & Next for Seedance."
                ),
                "intent": "generate_image",
                "phase": "storyboard_running",
                "suggested_actions": [],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": SEEDANCE_VIDEO_MODEL,
                "image_prompt": img0,
                "video_prompt": vid,
                "approved_image_url": None,
                "product_reference_url": product_ref or None,
                "storyboard_scenes": scenes,
                "status": "queued",
                "job_id": job_id,
                "media_mode": "storyboard",
                "model": img_model,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
                "error": None,
            }

        job_id = await _start_job(
            tenant_id=tenant_id,
            media_mode="image",
            model=img_model,
            prompt=prompt,
            duration_seconds=out_duration,
            aspect=out_aspect,
            resolution=resolution,
            sound_on=False,
            seed_image_url=None,
            product_name=product_name,
            brand_name=brand_name,
            product_reference_url=product_ref or None,
        )
        verb = "Regenerating" if action_norm == "regenerate_image" else "Generating"
        ref_note = (
            " Matching your attached product photo."
            if product_ref
            else ""
        )
        return {
            "assistant_message": (
                f"{verb} background still with GPT Image 2.{ref_note} "
                "When it lands, review it — Regenerate with notes, or Approve & Next to animate with Seedance 2.0."
            ),
            "intent": "generate_image",
            "phase": "image_running",
            "suggested_actions": [],
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": SEEDANCE_VIDEO_MODEL,
            "image_prompt": prompt,
            "video_prompt": video_prompt
            or _heuristic_timed_motion(
                user_brief=last_user or prompt,
                image_prompt=prompt,
                video_prompt="",
                duration_seconds=out_duration,
                sound_on=sound_on,
            ),
            "approved_image_url": None,
            "product_reference_url": product_ref or None,
            "status": "queued",
            "job_id": job_id,
            "media_mode": "image",
            "model": img_model,
            "duration_seconds": out_duration,
            "aspect": out_aspect,
            "error": None,
        }

    if action_norm in {"approve_next", "generate_video"}:
        # Approved GPT still drives video — never substitute the raw product photo as the seed.
        seed = (approved_image_url or "").strip()
        motion = (video_prompt or image_prompt or last_user or "").strip()
        if not motion:
            return {
                "assistant_message": "Approve a still first, or describe the motion for Seedance.",
                "intent": "reply",
                "phase": "awaiting_image" if not seed else "awaiting_video",
                "suggested_actions": ["generate_image"] if not seed else ["approve_next"],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": SEEDANCE_VIDEO_MODEL,
                "image_prompt": image_prompt or None,
                "video_prompt": video_prompt or None,
                "approved_image_url": seed or None,
                "product_reference_url": product_ref or None,
                "status": "ok",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
                "error": None,
            }
        if not seed:
            return {
                "assistant_message": (
                    "Approve a generated still first (or Generate image with your product photo attached). "
                    "The product photo alone isn’t used as the video seed."
                ),
                "intent": "reply",
                "phase": "awaiting_image",
                "suggested_actions": ["generate_image"],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": SEEDANCE_VIDEO_MODEL,
                "image_prompt": image_prompt or None,
                "video_prompt": motion,
                "approved_image_url": None,
                "product_reference_url": product_ref or None,
                "status": "ok",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
                "error": None,
            }
        if not ark_configured():
            return {
                "assistant_message": "Seedance isn’t configured — set ARK_API_KEY for BytePlus Seedance 2.0.",
                "intent": "reply",
                "phase": "awaiting_video",
                "suggested_actions": ["approve_next"],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": SEEDANCE_VIDEO_MODEL,
                "image_prompt": image_prompt or None,
                "video_prompt": motion,
                "approved_image_url": seed or None,
                "product_reference_url": product_ref or None,
                "status": "ok",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
                "error": None,
            }

        brief_for_motion = _find_full_user_brief(messages, last_user)
        from app.services.creative_studio_storyboard import (
            build_storyboard_video_prompt,
            looks_like_multi_scene_brief,
            parse_storyboard_scenes,
        )

        if looks_like_multi_scene_brief(brief_for_motion):
            board = parse_storyboard_scenes(
                brief_for_motion, product_name=product_name or ""
            )
            if len(board) >= 2:
                # The complete authored brief is authoritative, including product/cast
                # constraints before the first timestamp and the closing narration.
                from app.services.creative_studio_timeline import explicit_shot_windows
                authored_windows = explicit_shot_windows(brief_for_motion)
                if authored_windows:
                    # Duration presets are coarse (for example 30s), while an authored
                    # brief can end at an exact time such as 26s. Generate the authored
                    # timeline instead of rejecting the harmless preset mismatch.
                    out_duration = max(5, min(120, int(round(authored_windows[-1][1]))))
                motion = (
                    brief_for_motion
                    if explicit_shot_windows(brief_for_motion, total=out_duration)
                    else build_storyboard_video_prompt(
                        board, duration_seconds=out_duration,
                        sound_on=sound_on, product_name=product_name or "",
                    )
                )

        if len(brief_for_motion) < 80:
            brief_for_motion = f"{image_prompt}\n{video_prompt}\n{last_user}".strip()

        motion = await _ensure_rich_motion_prompt(
            model_slug=model_slug,
            user_brief=brief_for_motion,
            image_prompt=image_prompt,
            video_prompt=motion,
            duration_seconds=out_duration,
            sound_on=sound_on,
            brand_name=brand_name,
            product_name=product_name,
        )
        motion = _with_product_fidelity(motion, product_ref or None)

        multi_beat = bool(
            re.search(r"(?i)\bCLIP\s*2\b|\bHOOK\b|\bBODY\b|\bScene\s*2\b", motion)
        ) or looks_like_multi_scene_brief(motion)
        job_id = await _start_job(
            tenant_id=tenant_id,
            media_mode="video",
            model=SEEDANCE_VIDEO_MODEL,
            prompt=motion,
            duration_seconds=out_duration,
            aspect=out_aspect,
            resolution=resolution,
            sound_on=sound_on,
            seed_image_url=seed or None,
            # The image the user approved is the exact opening composition for
            # every video, including multi-scene stories. Later storyboard
            # frames remain references; they must not demote the approved still.
            seed_image_role="first_frame",
            product_name=product_name,
            brand_name=brand_name,
            product_reference_url=product_ref or None,
            logo_reference_url=logo_ref or None,
            additional_reference_urls=extra_refs,
            reference_assets=reference_assets,
            source_brief=full_brief,
            storyboard_image_urls=[
                u for u in (storyboard_image_urls or []) if (u or "").strip()
            ][:9],
        )
        audio_note = "with native audio" if sound_on else "silent"
        return {
            "assistant_message": (
                f"Approved. Queuing Seedance 2.0 · {out_duration}s · "
                f"{out_aspect.replace('/', ':')} · {audio_note}. "
                "Driving the FULL timed story from your brief"
                + (
                    " (approved still as opening frame, then progressing through each beat)."
                )
                + (" Product photo fidelity kept in the motion brief." if product_ref else "")
            ),
            "intent": "generate_video",
            "phase": "video_running",
            "suggested_actions": [],
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": SEEDANCE_VIDEO_MODEL,
            "image_prompt": image_prompt or None,
            "video_prompt": motion,
            "approved_image_url": seed or None,
            "product_reference_url": product_ref or None,
            "status": "queued",
            "job_id": job_id,
            "media_mode": "video",
            "model": SEEDANCE_VIDEO_MODEL,
            "duration_seconds": out_duration,
            "aspect": out_aspect,
            "error": None,
        }

    # ── Ask / Auto continue via LLM ──────────────────────────────────────────
    if mode_norm == "ask":
        parsed = await _llm_plan(
            model_slug=model_slug,
            mode_norm=mode_norm,
            duration_seconds=out_duration,
            aspect=out_aspect,
            sound_on=sound_on,
            brand_name=brand_name,
            product_name=product_name,
            attachments=attachments,
            messages=messages,
            phase=phase or "ask",
            image_prompt=image_prompt,
            video_prompt=video_prompt,
            approved_image_url=approved_image_url,
            revision_notes=revision_notes,
        )
        return {
            "assistant_message": str(parsed.get("assistant_message") or "Ask me anything about the ad.").strip(),
            "intent": "reply",
            "phase": phase or "ask",
            "suggested_actions": [],
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": SEEDANCE_VIDEO_MODEL,
            "image_prompt": str(parsed.get("image_prompt") or image_prompt or "") or None,
            "video_prompt": str(parsed.get("video_prompt") or video_prompt or "") or None,
            "approved_image_url": approved_image_url or None,
            "status": "ok",
            "job_id": None,
            "media_mode": None,
            "model": None,
            "duration_seconds": out_duration,
            "aspect": out_aspect,
            "error": None,
        }

    parsed = await _llm_plan(
        model_slug=model_slug,
        mode_norm=mode_norm,
        duration_seconds=out_duration,
        aspect=out_aspect,
        sound_on=sound_on,
        brand_name=brand_name,
        product_name=product_name,
        attachments=attachments,
        messages=messages,
        phase=phase or "planning",
        image_prompt=image_prompt,
        video_prompt=video_prompt,
        approved_image_url=approved_image_url,
        revision_notes=revision_notes,
    )

    intent = str(parsed.get("intent") or "reply").strip().lower()
    if mode_norm == "generate" and intent == "reply":
        intent = "draft_plan"

    # Heuristic: user wants production → draft plan
    if intent == "reply" and last_user:
        low = last_user.lower()
        if any(
            k in low
            for k in (
                "generate",
                "make a video",
                "create a video",
                "make me",
                "ugc",
                "product video",
                "animate",
                "seedance",
                "ad for",
                "commercial",
            )
        ):
            intent = "draft_plan"

    img_p = str(parsed.get("image_prompt") or image_prompt or "").strip()
    vid_p = str(parsed.get("video_prompt") or video_prompt or "").strip()
    out_aspect = _normalize_aspect(str(parsed.get("aspect") or ""), out_aspect)
    assistant_message = str(parsed.get("assistant_message") or "").strip()
    suggested = parsed.get("suggested_actions")
    if not isinstance(suggested, list):
        suggested = []
    suggested = [str(a) for a in suggested if str(a) in ACTIONS]

    if intent == "generate_image" and img_p:
        # Honor LLM choice to start image immediately
        return await run_creative_studio_chat_turn(
            tenant_id=tenant_id,
            messages=messages,
            mode=mode_norm,
            chat_model=chat_model,
            duration_seconds=out_duration,
            aspect=out_aspect,
            resolution=resolution,
            sound_on=sound_on,
            attachment_urls=attachments,
            brand_name=brand_name,
            product_name=product_name,
            action="generate_image",
            image_prompt=img_p,
            video_prompt=vid_p,
            approved_image_url=approved_image_url,
            image_model=img_model,
            revision_notes="",
            phase="image_running",
            product_reference_url=product_ref,
            logo_reference_url=logo_ref,
            additional_reference_urls=extra_refs,
            reference_assets=reference_assets,
            storyboard_image_urls=storyboard_image_urls,
        )

    if intent == "generate_video" and approved_image_url:
        return await run_creative_studio_chat_turn(
            tenant_id=tenant_id,
            messages=messages,
            mode=mode_norm,
            chat_model=chat_model,
            duration_seconds=out_duration,
            aspect=out_aspect,
            resolution=resolution,
            sound_on=sound_on,
            attachment_urls=attachments,
            brand_name=brand_name,
            product_name=product_name,
            action="approve_next",
            image_prompt=img_p,
            video_prompt=vid_p,
            approved_image_url=approved_image_url,
            image_model=img_model,
            revision_notes="",
            phase="video_running",
            product_reference_url=product_ref,
            logo_reference_url=logo_ref,
            additional_reference_urls=extra_refs,
            reference_assets=reference_assets,
            storyboard_image_urls=storyboard_image_urls,
        )

    if intent in {"draft_plan", "generate_video"} or (intent == "reply" and mode_norm == "generate"):
        if not img_p and last_user:
            img_p = last_user[:2000]
        # Fast path for draft — do NOT block on a second LLM expand (that felt "stuck").
        # Full timed expand runs at Approve → Seedance.
        if not vid_p or _motion_prompt_is_weak(vid_p):
            vid_p = _heuristic_timed_motion(
                user_brief=last_user or img_p,
                image_prompt=img_p,
                video_prompt=vid_p or "",
                duration_seconds=out_duration,
                sound_on=sound_on,
            )
        if not assistant_message:
            assistant_message = (
                "Here’s the production plan from your full brief: GPT Image 2 opening still, then "
                "Seedance 2.0 playing the timed story beats."
            )
        if "generate_image" not in suggested:
            suggested = ["generate_image"]

        # Agent-style Auto/Generate: don't stop at the plan — start the still now.
        if mode_norm in {"auto", "generate"} and img_p:
            chained = await run_creative_studio_chat_turn(
                tenant_id=tenant_id,
                messages=messages,
                mode=mode_norm,
                chat_model=chat_model,
                duration_seconds=out_duration,
                aspect=out_aspect,
                resolution=resolution,
                sound_on=sound_on,
                attachment_urls=attachments,
                brand_name=brand_name,
                product_name=product_name,
                action="generate_image",
                image_prompt=img_p,
                video_prompt=vid_p,
                approved_image_url=approved_image_url,
                image_model=img_model,
                revision_notes="",
                phase="image_running",
                product_reference_url=product_ref,
                logo_reference_url=logo_ref,
                additional_reference_urls=extra_refs,
                reference_assets=reference_assets,
                storyboard_image_urls=storyboard_image_urls,
            )
            plan_lead = (assistant_message or "").strip()
            gen_msg = str(chained.get("assistant_message") or "").strip()
            chained["assistant_message"] = (
                f"{plan_lead}\n\n{gen_msg}" if plan_lead and gen_msg else (gen_msg or plan_lead)
            )
            chained["image_prompt"] = img_p
            chained["video_prompt"] = vid_p
            if product_ref:
                chained["product_reference_url"] = product_ref
            return chained

        return {
            "assistant_message": (
                f"{assistant_message} Click Generate image when ready."
            ),
            "intent": "draft_plan",
            "phase": "awaiting_image",
            "suggested_actions": suggested,
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": SEEDANCE_VIDEO_MODEL,
            "image_prompt": img_p or None,
            "video_prompt": vid_p or None,
            "approved_image_url": approved_image_url or None,
            "product_reference_url": product_ref or None,
            "status": "ok",
            "job_id": None,
            "media_mode": None,
            "model": None,
            "duration_seconds": out_duration,
            "aspect": out_aspect,
            "error": None,
        }

    return {
        "assistant_message": assistant_message
        or "Tell me what ad you want — I’ll draft the still, then animate it with Seedance.",
        "intent": "reply",
        "phase": phase or "idle",
        "suggested_actions": suggested,
        "chat_model": model_slug,
        "image_model": img_model,
        "video_model": SEEDANCE_VIDEO_MODEL,
        "image_prompt": img_p or None,
        "video_prompt": vid_p or None,
        "approved_image_url": approved_image_url or None,
        "status": "ok",
        "job_id": None,
        "media_mode": None,
        "model": None,
        "duration_seconds": out_duration,
        "aspect": out_aspect,
        "error": None,
    }
