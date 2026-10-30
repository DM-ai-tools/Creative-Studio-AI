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
from app.services.media.gemini_omni_provider import (
    gemini_omni_configured,
    is_gemini_omni_model,
)

logger = logging.getLogger(__name__)

SEEDANCE_VIDEO_MODEL = "ark-seedance-2-0"
DEFAULT_IMAGE_MODEL = "openai-gpt-image-2"


def _resolve_video_model(video_model: str | None) -> str:
    from app.services.media.byteplus_seedance_provider import is_byteplus_seedance_model

    candidate = (video_model or SEEDANCE_VIDEO_MODEL).strip()
    if is_byteplus_seedance_model(candidate) or is_gemini_omni_model(candidate):
        return candidate
    return SEEDANCE_VIDEO_MODEL


def _seedance_model_label(model: str) -> str:
    from app.services.media.byteplus_seedance_client import is_seedance_25_model

    if is_gemini_omni_model(model):
        return "Gemini Omni 1.1 Flash"
    return "Seedance 2.5" if is_seedance_25_model(model) else "Seedance 2.0"


def _video_clip_cap_seconds(model: str) -> int:
    from app.services.media.byteplus_seedance_client import seedance_clip_cap_seconds

    return 10 if is_gemini_omni_model(model) else seedance_clip_cap_seconds(model)

# Explicit UI / client actions (approve-before-video, like Higgsfield Supercomputer)
ACTIONS = frozenset(
    {
        "continue",
        "generate_image",
        "regenerate_image",
        "approve_next",
        "generate_video",
        "generate_storyboard",
        "generate_next_chapter_image",
        "generate_broll_image",
        "generate_all_broll",
        "regenerate_broll_image",
        "approve_broll",
        "approve_all_broll",
    }
)


def _needs_chapter_image_staging(
    *, prompt_only_video: bool, duration_seconds: int, clip_cap: int
) -> bool:
    """Image-first long films: one GPT still per chapter, approve between each."""
    return not prompt_only_video and int(duration_seconds) > int(clip_cap)


def _film_chapter_count(duration_seconds: int, clip_cap: int) -> int:
    from app.services.creative_studio_job_service import _seedance_segment_durations

    return len(_seedance_segment_durations(int(duration_seconds), int(clip_cap)))


def _chapter_duration(duration_seconds: int, clip_cap: int, chapter_index: int) -> int:
    from app.services.creative_studio_job_service import _seedance_segment_durations

    durations = _seedance_segment_durations(int(duration_seconds), int(clip_cap))
    index = max(0, min(int(chapter_index), len(durations) - 1))
    return int(durations[index])


def _locked_chapter_duration(
    memory: dict[str, Any], chapter_index: int, *, fallback: int
) -> int:
    """Use the authored chapter boundary stored in production memory.

    Equal duration splitting is only a fallback for unstructured briefs. Once a
    timed prompt has been locked, its packed scene boundaries are authoritative.
    """
    shots = list(memory.get("shot_list") or [])
    index = int(chapter_index)
    if index < 0 or index >= len(shots):
        return int(fallback)
    start = float(shots[index].get("start") or 0.0)
    end = float(shots[index].get("end") or start)
    duration = int(round(end - start))
    return duration if duration > 0 else int(fallback)

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
  "aspect": "9/16" | "1/1" | "16/9" | "4/3" | "4/5",
  "suggested_actions": ["generate_image"]
}

CRITICAL:
- Multi-scene briefs → fill "scenes" array (one entry per Scene). image_prompt = Scene 1 only.
- Each scene image_prompt = that scene's keyframe ONLY (do not mash Scene 1 + product reveal into one frame).
- NO burned-in text in image prompts (overlays go in scenes[].overlays and video_prompt).
- video_prompt must include every scene as timed CLIP beats + overlay lines.
- Product photo attachments = PRODUCT LOCK for product scenes only.
- Character/presenter photo attachments = CHARACTER REFERENCE only (general visual guide for
  clothing, age range, hairstyle, body type, presentation). Never write CHARACTER LOCK or ask
  to preserve exact facial identity — generate a fictional presenter with similar characteristics.
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
    allowed = {"9/16", "1/1", "16/9", "4/3", "4/5", "1/4"}
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
    # Production briefs commonly put a compact runtime in the title, such as
    # "26s LIVE-ACTION AD". Read that before estimating from document length.
    compact_seconds = re.search(r"(?i)\b(\d{1,3})\s*s\b", raw)
    if compact_seconds:
        return max(5, min(120, int(compact_seconds.group(1))))
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
    from app.services.media.byteplus_seedream_client import seedream_configured

    if openai_configured():
        return DEFAULT_IMAGE_MODEL
    if seedream_configured():
        return "ark-seedream-5-0-lite"
    from app.services.media.higgsfield_models import higgsfield_configured
    if higgsfield_configured():
        return "hf-text2image-soul-v2"
    return DEFAULT_IMAGE_MODEL


def _image_generation_configured() -> bool:
    from app.services.media.byteplus_seedream_client import seedream_configured
    from app.services.media.higgsfield_models import higgsfield_configured
    from app.services.media.openai_image_catalog import openai_configured

    return bool(openai_configured() or seedream_configured() or higgsfield_configured())


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
        "Image models: GPT Image 2 or BytePlus Seedream 5.0 (Lite / Pro / Flash).",
        "Video model: Seedance 2.0 or 2.5 (ark-seedance-2-0 / ark-seedance-2-5).",
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
    speech_mode: str = "external_voiceover",
    seed_image_role: str = "first_frame",
    product_name: str = "",
    brand_name: str = "",
    brand_id: str = "",
    brief_id: str = "",
    user_id: str = "",
    product_reference_url: str | None = None,
    logo_reference_url: str | None = None,
    additional_reference_urls: list[str] | None = None,
    reference_assets: list[dict[str, str]] | None = None,
    source_brief: str = "",
    storyboard_scenes: list[dict[str, Any]] | None = None,
    storyboard_image_urls: list[str] | None = None,
    require_storyboard_coverage: bool = True,
    prompt_only_video: bool = False,
    preserve_image_text: bool = False,
    session_id: str = "",
    chapter_image_staging: bool = False,
    film_chapter_index: int = 0,
    film_total_chapters: int = 1,
    full_film_duration: int | None = None,
    accumulated_segment_paths: list[str] | None = None,
    continuity_style_url: str | None = None,
    broll_index: int | None = None,
    broll_title: str = "",
    broll_segments: list[dict[str, Any]] | None = None,
    broll_plan: list[dict[str, Any]] | None = None,
    clone_mode: bool = False,
    clone_scene_id: str = "",
    clone_count: int = 4,
    clone_identity_prompt: str = "",
    background_only_image: bool = False,
) -> str:
    import asyncio

    from app.services.creative_studio_job_service import (
        create_job,
        run_creative_studio_job,
    )
    from app.services.usage_tracker import get_usage_context

    ctx = get_usage_context()
    if not brand_id:
        brand_id = str(ctx.get("brand_id") or "")
    if not brief_id:
        brief_id = str(ctx.get("brief_id") or "")
    if not user_id:
        user_id = str(ctx.get("user_id") or "")
    if not brand_name:
        brand_name = str(ctx.get("brand_name") or "")

    clip_cap = _video_clip_cap_seconds(model)

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
            "speech_mode": (
                speech_mode
                if speech_mode in {"native_presenter", "external_voiceover"}
                else "external_voiceover"
            ),
            "product_name": product_name or "",
            "brand_name": brand_name or "",
            "brand_id": str(brand_id or "").strip() or None,
            "brief_id": str(brief_id or "").strip() or None,
            "user_id": str(user_id or "").strip() or None,
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
            "require_storyboard_coverage": bool(require_storyboard_coverage),
            "prompt_only_video": bool(prompt_only_video),
            "preserve_image_text": bool(preserve_image_text),
            # Long Creative Studio films are reviewed one provider-sized chapter
            # at a time. The next paid call starts only after user approval.
            "interactive_staging": (
                media_mode == "video"
                and duration_seconds > clip_cap
                and not chapter_image_staging
            ),
            "chapter_image_staging": bool(chapter_image_staging),
            "film_chapter_index": int(film_chapter_index),
            "film_total_chapters": int(film_total_chapters),
            "full_film_duration": int(full_film_duration or duration_seconds),
            "accumulated_segment_paths": list(accumulated_segment_paths or []),
            "continuity_style_url": str(continuity_style_url or "").strip() or None,
            "broll_index": int(broll_index) if broll_index else None,
            "broll_title": str(broll_title or "").strip() or None,
            "broll_segments": list(broll_segments or []),
            "broll_plan": list(broll_plan or []),
            "clone_mode": bool(clone_mode),
            "clone_scene_id": str(clone_scene_id or "").strip(),
            "clone_count": max(2, min(6, int(clone_count or 4))),
            "clone_identity_prompt": str(clone_identity_prompt or "").strip(),
            # Keep a selected presenter available for Seedance without feeding
            # that face into GPT Image 2 supporting-scene generation.
            "background_only_image": bool(background_only_image),
            # Stable key for the immutable production bible and chapter ledger.
            "creative_studio_session_id": session_id,
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
        if re.match(r"(?i)^(approve|generate|regenerate)\b", low) and len(content) < 320:
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
    session_id: str = "",
    mode: str = "auto",
    chat_model: str | None = None,
    duration_seconds: int | None = None,
    aspect: str = "9/16",
    resolution: str = "1080p",
    sound_on: bool = True,
    speech_mode: str = "native_presenter",
    attachment_urls: list[str] | None = None,
    brand_name: str = "",
    brand_id: str = "",
    brief_id: str = "",
    user_id: str = "",
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
    prompt_only_video: bool = False,
    preserve_image_text: bool = False,
    video_model: str | None = None,
    chapter_index: int | None = None,
    continuity_style_url: str = "",
    accumulated_segment_paths: list[str] | None = None,
    broll_index: int | None = None,
    approved_broll_url: str = "",
    approved_broll_byteplus_url: str = "",
    broll_board_approvals: list[dict[str, Any]] | None = None,
    clone_mode: bool = False,
    clone_scene_id: str = "",
    clone_count: int = 4,
) -> dict[str, Any]:
    """
    Creative Studio production turn. Direct Seedance is the default frontend
    workflow; callers may opt into a reviewed GPT Image 2 start frame.
    """
    from app.services.usage_tracker import set_usage_context

    set_usage_context(
        tenant_id=tenant_id,
        user_id=user_id or None,
        brand_id=brand_id or None,
        brand_name=(brand_name or "").strip() or None,
        brief_id=brief_id or None,
        operation="creative_studio_chat",
    )
    from app.services.media.byteplus_seedance_client import (
        ark_configured,
        ark_configured_for_model,
    )
    from app.services.media.higgsfield_models import higgsfield_configured
    from app.services.media.openai_image_catalog import openai_configured

    mode_norm = (mode or "auto").strip().lower()
    if mode_norm not in {"auto", "ask", "generate"}:
        mode_norm = "auto"

    speech_mode = (speech_mode or "native_presenter").strip().lower()
    if speech_mode not in {"native_presenter", "external_voiceover"}:
        speech_mode = "native_presenter"

    action_norm = (action or "continue").strip().lower()
    if action_norm not in ACTIONS:
        action_norm = "continue"

    last_user = ""
    for m in reversed(messages):
        if str(m.get("role") or "") == "user" and str(m.get("content") or "").strip():
            last_user = str(m.get("content") or "").strip()
            break

    active_video_model = _resolve_video_model(video_model)
    video_model_label = _seedance_model_label(active_video_model)

    # Old direct-video clients may still submit a stale image action. Preserve
    # that behaviour only when direct mode is explicitly requested. Image-first
    # mode is opt-in and must be allowed to reach GPT Image 2.
    clone_mode = bool(clone_mode)
    clone_count = max(2, min(6, int(clone_count or 4)))
    prompt_only_video = bool(prompt_only_video) and not clone_mode
    from app.services.creative_studio_broll import is_production_setup_only_message

    setup_only = is_production_setup_only_message(last_user)
    # Detect standalone IMAGE block pastes — must always go to B-roll still generation
    import re as _re
    from app.services.creative_studio_broll import is_master_production_brief

    _is_master_brief = is_master_production_brief(last_user)
    _is_inline_broll_block = bool(
        not _is_master_brief
        and last_user
        and _re.search(r"(?im)^\s*IMAGE\s+\d+\s*[-–—:]", last_user)
        and _re.search(r"(?i)scene\s*timing|image\s+generation\s+prompt", last_user)
    )

    if setup_only and action_norm in {"generate_video", "approve_next"}:
        action_norm = "continue"
    # Full master brief paste → auto-generate all B-roll images first
    if _is_master_brief and action_norm in {
        "generate_video", "approve_next", "continue", "generate_image",
        "regenerate_image", "generate_storyboard",
    }:
        action_norm = "generate_all_broll"
    if _is_inline_broll_block and action_norm in {
        "generate_video", "approve_next", "continue", "generate_image", "regenerate_image",
    }:
        # Multiple IMAGE blocks in one paste → batch generate all at once
        _inline_block_count = len(_re.findall(r"(?:^|\n)\s*IMAGE\s+\d+\s*[-–—:]", last_user, _re.I))
        action_norm = "generate_all_broll" if _inline_block_count > 1 else "generate_broll_image"
    if (
        prompt_only_video
        and not setup_only
        and not _is_inline_broll_block
        and not _is_master_brief
        and mode_norm != "ask"
        and action_norm in {
            "continue",
            "generate_image",
            "regenerate_image",
            "generate_storyboard",
            "approve_next",
        }
    ):
        action_norm = "generate_video"

    attachments = [u for u in (attachment_urls or []) if (u or "").strip()]
    product_ref = (product_reference_url or "").strip() or (attachments[0] if attachments and not reference_assets else "")
    logo_ref = (logo_reference_url or "").strip()
    if product_ref and logo_ref and product_ref == logo_ref:
        product_ref = ""
    extra_refs = [
        u.strip()
        for u in (additional_reference_urls or [])
        if (u or "").strip() and u.strip() not in {product_ref, logo_ref}
    ][:7]
    selected_character_url = next(
        (
            str(asset.get("url") or "").strip()
            for asset in (reference_assets or [])
            if isinstance(asset, dict)
            and str(asset.get("role") or "").strip().lower() == "character"
            and str(asset.get("url") or "").strip()
        ),
        "",
    )

    def _fmt_time(seconds: float) -> str:
        m, s = divmod(int(round(seconds)), 60)
        return f"{m:02d}:{s:02d}"

    def _seedance_presenter_note() -> str:
        if selected_character_url:
            return (
                "Your selected Character remains locked as the presenter identity reference "
                "for Seedance. Click Approve & Next → Seedance video."
            )
        return (
            "No Character photo is selected, so Seedance will create a fictional presenter "
            "from your script. Click Approve & Next → Seedance video."
        )

    def _proof_still_url() -> str | None:
        """Uploaded stat/dashboard proof — usually tagged Reference, not Product."""
        for asset in reference_assets or []:
            if not isinstance(asset, dict):
                continue
            role = str(asset.get("role") or "").strip().lower()
            url = str(asset.get("url") or "").strip()
            if role in {"reference", "product", "scene"} and url:
                return url
        for url in extra_refs:
            if url:
                return url
        return product_ref or None
    model_slug = (
        resolve_prompt_llm_model(chat_model)
        if chat_model and chat_model != "auto"
        else default_prompt_llm_model()
    )
    img_model = "openai-gpt-image-2" if clone_mode else ((image_model or "").strip() or _default_image_model())
    full_brief = _find_full_user_brief(messages, last_user)
    requested_duration = (
        _normalize_duration(duration_seconds, _estimate_script_duration(full_brief))
        if duration_seconds is not None
        else _estimate_script_duration(full_brief)
    )
    out_duration = requested_duration
    out_aspect = _normalize_aspect(aspect, "9/16")
    clip_cap = _video_clip_cap_seconds(active_video_model)
    chapter_staging = _needs_chapter_image_staging(
        prompt_only_video=bool(prompt_only_video),
        duration_seconds=out_duration,
        clip_cap=clip_cap,
    )
    film_chapters = _film_chapter_count(out_duration, clip_cap) if chapter_staging else 1
    active_chapter_index = max(0, int(chapter_index or 0))
    next_chapter_image = action_norm == "generate_next_chapter_image"
    if next_chapter_image:
        action_norm = "generate_image"

    def _ensure_broll_memory() -> dict[str, Any]:
        from app.services.creative_studio_broll import parse_broll_images
        from app.services.creative_studio_production_memory import (
            ensure_broll_plan,
            ensure_production_memory,
            load_production_memory,
            normalized_reference_lock,
            save_production_memory,
        )
        from app.services.creative_studio_video_finishing import extract_voiceover_events

        session_key = (session_id or "").strip() or "draft"

        def _stamp_session(mem: dict[str, Any]) -> dict[str, Any]:
            if mem and not str(mem.get("session_id") or "").strip():
                mem["session_id"] = session_key
            return mem

        existing = load_production_memory(tenant_id, session_id)
        plan = parse_broll_images(full_brief)
        if existing:
            _stamp_session(existing)
            if plan and not existing.get("broll_plan"):
                ensure_broll_plan(existing, plan)
                save_production_memory(tenant_id, existing)
            elif (
                plan
                and not existing.get("approved_broll")
                and list(existing.get("broll_plan") or []) != plan
            ):
                # Parser improvements or prompt corrections may change an
                # unapproved board. Refresh it safely before any still is
                # locked; approved B-roll remains immutable.
                existing["broll_plan"] = plan
                save_production_memory(tenant_id, existing)
            if existing.get("broll_plan") or existing.get("approved_broll"):
                return existing
        voice_events = extract_voiceover_events(full_brief, duration_seconds=out_duration)
        refs = normalized_reference_lock(
            list(reference_assets or []),
            product_reference_url=product_ref or None,
            logo_reference_url=logo_ref or None,
        )
        memory = ensure_production_memory(
            tenant_id=tenant_id,
            session_id=session_id or "draft",
            prompt=full_brief,
            duration_seconds=out_duration,
            clip_cap=clip_cap,
            aspect=out_aspect,
            resolution=resolution or "1080p",
            model=active_video_model,
            brand_name=brand_name,
            product_name=product_name,
            voice_events=voice_events,
            references=refs,
        )
        ensure_broll_plan(memory, plan)
        _stamp_session(memory)
        if plan and not (existing and existing.get("broll_plan")):
            save_production_memory(tenant_id, memory)
        return memory

    def _production_lock_reply() -> dict[str, Any]:
        from app.services.creative_studio_production_memory import pending_broll_indices

        memory = _ensure_broll_memory()
        plan = list(memory.get("broll_plan") or [])
        pending = pending_broll_indices(memory) if plan else []
        chapter_count = len(memory.get("shot_list") or [])
        return {
            "assistant_message": (
                "Production locked — timeline and settings saved for this chat. "
                f"{chapter_count} Seedance chapter(s) are mapped from your scene times. "
                "Seedance is not running yet. "
                + (
                    f"Generate and approve B-roll stills ({len(pending)} of {len(plan)} pending), "
                    "then ask to start chapter 1."
                    if plan
                    else "Paste each IMAGE 1–4 block (or generate stills one by one), approve them, "
                    "then send your chapter 1 Seedance prompt."
                )
            ),
            "intent": "reply",
            "phase": "awaiting_broll" if plan else "planning",
            "suggested_actions": (
                ["generate_all_broll", "generate_broll_image"] if pending else ["generate_broll_image"]
            ),
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": active_video_model,
            "broll_index": pending[0] if pending else (int(plan[0]["index"]) if plan else None),
            "status": "ok",
            "job_id": None,
            "media_mode": None,
            "model": None,
            "duration_seconds": out_duration,
            "aspect": out_aspect,
            "error": None,
        }

    if setup_only and action_norm == "continue":
        return _production_lock_reply()

    # A master brief with explicit supporting-image blocks should enter the
    # B-roll board workflow immediately. Otherwise the full presenter brief can
    # be mistaken for one opening-still prompt and GPT Image 2 may draw the
    # selected presenter into the background asset.
    if action_norm == "generate_image" and not clone_mode:
        from app.services.creative_studio_broll import parse_broll_images

        if parse_broll_images(full_brief):
            action_norm = "generate_all_broll"

    # ── Explicit pipeline actions (no LLM required) ──────────────────────────
    if action_norm == "approve_broll":
        from app.services.creative_studio_production_memory import (
            approve_broll_still,
            pending_broll_indices,
        )

        url = (approved_broll_url or approved_image_url or "").strip()
        idx = int(broll_index or 0)
        if not url or idx < 1:
            return {
                "assistant_message": "Approve a B-roll still first (Generate B-roll image, then Approve B-roll).",
                "intent": "reply",
                "phase": "awaiting_broll",
                "suggested_actions": ["generate_broll_image"],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": active_video_model,
                "status": "failed",
                "error": "broll_not_approved",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
            }
        memory = _ensure_broll_memory()
        item = next(
            (row for row in (memory.get("broll_plan") or []) if int(row.get("index") or 0) == idx),
            {"title": f"B-roll {idx}"},
        )
        approve_broll_still(
            tenant_id,
            memory,
            index=idx,
            url=url,
            title=str(item.get("title") or f"B-roll {idx}"),
            byteplus_url=(approved_broll_byteplus_url or "").strip() or None,
        )
        pending = pending_broll_indices(memory)
        if pending:
            next_actions = ["generate_all_broll", "generate_broll_image"]
            approve_msg = (
                f"Approved B-roll IMAGE {idx}: {item.get('title')}. "
                f"{len(pending)} B-roll still(s) remaining — generate all at once or one at a time."
            )
        else:
            next_actions = ["approve_next"]
            # Smart chapter guidance from stored scene plan
            scene_plan = list(memory.get("scene_plan") or [])
            if scene_plan:
                first_seedance = next(
                    (s for s in scene_plan if s.get("type") in {"presenter", "broll"}),
                    None,
                )
                if first_seedance:
                    t_start = first_seedance["start"]
                    t_end = scene_plan[-1]["end"]
                    seedance_scenes = [s for s in scene_plan if s.get("type") in {"presenter", "broll"}]
                    approve_msg = (
                        f"✅ All {len(memory.get('broll_plan') or [])} B-roll stills approved and locked!\n\n"
                        f"Your production has {len(seedance_scenes)} Seedance scene(s) across "
                        f"{int(round(t_end - t_start))}s. Send this to start:\n\n"
                        f"**Start Seedance from {_fmt_time(t_start)}–{_fmt_time(t_end)}. "
                        "Use approved B-roll stills at their locked scene times. "
                        "Native Australian English female presenter throughout.**"
                    )
                else:
                    approve_msg = f"All B-roll stills approved. {_seedance_presenter_note()}"
            else:
                approve_msg = f"All B-roll stills approved. {_seedance_presenter_note()}"
        return {
            "assistant_message": approve_msg,
            "intent": "reply",
            "phase": "awaiting_broll" if pending else "awaiting_video",
            "suggested_actions": next_actions,
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": active_video_model,
            "broll_index": pending[0] if pending else None,
            "status": "ok",
            "job_id": None,
            "media_mode": None,
            "model": None,
            "duration_seconds": out_duration,
            "aspect": out_aspect,
            "error": None,
        }

    if action_norm == "approve_all_broll":
        from app.services.creative_studio_production_memory import (
            approve_broll_still,
            pending_broll_indices,
        )

        memory = _ensure_broll_memory()
        plan = list(memory.get("broll_plan") or [])
        rows = [
            row
            for row in (broll_board_approvals or [])
            if isinstance(row, dict)
            and int(row.get("index") or 0) >= 1
            and str(row.get("url") or "").strip()
        ]
        if not rows:
            return {
                "assistant_message": (
                    "No B-roll stills to approve. Generate the B-roll board first, "
                    "then approve each image or use Approve all."
                ),
                "intent": "reply",
                "phase": "awaiting_broll",
                "suggested_actions": ["generate_all_broll", "generate_broll_image"],
                "status": "failed",
                "error": "broll_board_empty",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
            }
        approved_count = 0
        for row in rows:
            idx = int(row["index"])
            url = str(row["url"]).strip()
            item = next(
                (p for p in plan if int(p.get("index") or 0) == idx),
                {"title": f"B-roll {idx}"},
            )
            approve_broll_still(
                tenant_id,
                memory,
                index=idx,
                url=url,
                title=str(item.get("title") or f"B-roll {idx}"),
                byteplus_url=str(row.get("byteplus_url") or "").strip() or None,
            )
            approved_count += 1
        pending = pending_broll_indices(memory)
        if pending:
            next_actions = ["generate_all_broll", "generate_broll_image"]
            msg = (
                f"Approved {approved_count} B-roll still(s). "
                f"{len(pending)} still(s) left — regenerate or generate the missing IMAGE(s)."
            )
            phase = "awaiting_broll"
        else:
            next_actions = ["approve_next"]
            msg = (
                f"All {approved_count} B-roll stills approved and locked for Seedance. "
                f"{_seedance_presenter_note()}"
            )
            phase = "awaiting_video"
        return {
            "assistant_message": msg,
            "intent": "reply",
            "phase": phase,
            "suggested_actions": next_actions,
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": active_video_model,
            "broll_index": pending[0] if pending else None,
            "status": "ok",
            "job_id": None,
            "media_mode": None,
            "model": None,
            "duration_seconds": out_duration,
            "aspect": out_aspect,
            "error": None,
        }

    if action_norm == "generate_all_broll":
        from app.services.creative_studio_broll import (
            _parse_standalone_image_block,
            parse_broll_images,
        )
        from app.services.creative_studio_production_memory import (
            ensure_broll_plan,
            pending_broll_indices,
            save_production_memory,
        )

        if not _image_generation_configured():
            return {
                "assistant_message": "Image generation isn't configured for B-roll stills.",
                "intent": "reply",
                "phase": "awaiting_broll",
                "suggested_actions": [],
                "status": "failed",
                "error": "image_not_configured",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
            }

        # Merge any IMAGE blocks pasted inline into the stored plan
        inline_items = parse_broll_images(last_user) if last_user else []
        if not inline_items and last_user:
            single = _parse_standalone_image_block(last_user)
            if single:
                inline_items = [single]

        memory = _ensure_broll_memory()
        plan = list(memory.get("broll_plan") or [])

        if inline_items:
            existing_indices = {int(r.get("index") or 0) for r in plan}
            changed = False
            for item in inline_items:
                idx = int(item.get("index") or 0)
                if idx not in existing_indices:
                    plan.append(item)
                    changed = True
                else:
                    plan = [
                        item if int(r.get("index") or 0) == idx else r
                        for r in plan
                    ]
                    changed = True
            if changed:
                ensure_broll_plan(memory, plan)
                if not str(memory.get("session_id") or "").strip():
                    memory["session_id"] = (session_id or "").strip() or "draft"
                save_production_memory(tenant_id, memory)

        # If this is a master brief, store the full scene plan and lock any
        # proof-tagged uploads as editor-only (never sent to Seedance/GPT Image 2)
        if _is_master_brief and last_user:
            from app.services.creative_studio_broll import parse_scene_plan
            scene_plan = parse_scene_plan(last_user)
            if scene_plan and not memory.get("scene_plan"):
                memory["scene_plan"] = scene_plan

            # Lock proof assets (editor-only composites) in memory
            proof_assets = [
                {"url": str(a.get("url") or "").strip(), "label": str(a.get("role") or "proof")}
                for a in (reference_assets or [])
                if str(a.get("role") or "").strip().lower() == "proof"
                and str(a.get("url") or "").strip()
            ]
            if proof_assets and not memory.get("proof_assets"):
                memory["proof_assets"] = proof_assets

            if not str(memory.get("session_id") or "").strip():
                memory["session_id"] = (session_id or "").strip() or "draft"
            save_production_memory(tenant_id, memory)
        if not plan:
            return {
                "assistant_message": (
                    "No IMAGE 1 / IMAGE 2 / … blocks found in your brief. "
                    "Add B-roll image sections with timing and prompts, then retry."
                ),
                "intent": "reply",
                "phase": "planning",
                "suggested_actions": ["generate_image"],
                "status": "failed",
                "error": "broll_plan_missing",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
            }
        pending = pending_broll_indices(memory)
        if pending:
            targets = [
                item for item in plan if int(item["index"]) in pending
            ]
        else:
            targets = list(plan)
        if not targets:
            return {
                "assistant_message": (
                    "All B-roll stills are already approved. "
                    "Generate the chapter opening presenter still next."
                ),
                "intent": "reply",
                "phase": "awaiting_image",
                "suggested_actions": ["generate_image"],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": active_video_model,
                "status": "ok",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
                "error": None,
            }
        scenes = [
            {
                "id": f"broll-{int(item['index'])}",
                "index": int(item["index"]),
                "title": f"IMAGE {item['index']} — {item.get('title')}",
                "image_prompt": str(item.get("image_prompt") or ""),
                "wants_readable_text": bool(item.get("wants_readable_text", True)),
            }
            for item in targets
        ]
        job_id = await _start_job(
            tenant_id=tenant_id,
            media_mode="broll_board",
            model=img_model,
            prompt=str(targets[0].get("image_prompt") or "B-roll still"),
            duration_seconds=out_duration,
            aspect=out_aspect,
            resolution=resolution,
            sound_on=False,
            seed_image_url=None,
            product_name=product_name,
            brand_name=brand_name,
            product_reference_url=None,
            logo_reference_url=logo_ref or None,
            additional_reference_urls=extra_refs,
            reference_assets=reference_assets,
            preserve_image_text=True,
            session_id=session_id,
            broll_plan=targets,
            storyboard_scenes=scenes,
        )
        titles = ", ".join(str(s.get("title") or "")[:36] for s in scenes[:5])
        extra = f" (+{len(scenes) - 5} more)" if len(scenes) > 5 else ""
        remaining = len(targets) < len(plan)
        scene_plan = list(memory.get("scene_plan") or [])
        seedance_scenes = [sc for sc in scene_plan if sc.get("type") in {"presenter", "broll"}]
        proof_assets = list(memory.get("proof_assets") or [])
        proof_note = (
            f" 🔒 {len(proof_assets)} proof asset(s) locked as editor-only composites "
            "(will NOT be sent to Seedance or GPT Image 2)."
            if proof_assets else ""
        )
        master_note = (
            f"\n\n📋 **Production parsed:** {len(scene_plan)} scenes total, "
            f"{len(seedance_scenes)} Seedance scene(s).{proof_note} "
            "After approving all B-roll stills, I'll guide you through each Seedance chapter in order."
            if _is_master_brief and scene_plan
            else ""
        )
        return {
            "assistant_message": (
                f"Generating {'remaining ' if remaining else 'all '}{len(scenes)} B-roll still(s) "
                f"({titles}{extra}). Review each — Regenerate any that look wrong, "
                f"then Approve all B-roll. Seedance uses these exact PNGs.{master_note}"
            ),
            "intent": "generate_image",
            "phase": "broll_board_running",
            "suggested_actions": [],
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": active_video_model,
            "image_prompt": str(targets[0].get("image_prompt") or ""),
            "storyboard_scenes": scenes,
            "status": "queued",
            "job_id": job_id,
            "media_mode": "broll_board",
            "model": img_model,
            "duration_seconds": out_duration,
            "aspect": out_aspect,
            "error": None,
        }

    if action_norm in {"generate_broll_image", "regenerate_broll_image"}:
        from app.services.creative_studio_production_memory import pending_broll_indices

        if not _image_generation_configured():
            return {
                "assistant_message": "Image generation isn't configured for B-roll stills.",
                "intent": "reply",
                "phase": "awaiting_broll",
                "suggested_actions": [],
                "status": "failed",
                "error": "image_not_configured",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
            }
        from app.services.creative_studio_broll import (
            _parse_standalone_image_block,
            parse_broll_images,
        )
        from app.services.creative_studio_production_memory import (
            ensure_broll_plan,
            save_production_memory,
        )

        # When the user pastes an IMAGE block as a standalone message it will be
        # shorter than the production-lock prompt, so _find_full_user_brief skips
        # it. Parse the current user message directly first.
        inline_items = parse_broll_images(last_user) if last_user else []
        # Fallback: try the more lenient standalone parser if the strict regex missed it
        if not inline_items and last_user:
            single = _parse_standalone_image_block(last_user)
            if single:
                inline_items = [single]

        memory = _ensure_broll_memory()
        plan = list(memory.get("broll_plan") or [])

        # Merge any new inline IMAGE blocks into the stored plan
        if inline_items:
            existing_indices = {int(r.get("index") or 0) for r in plan}
            changed = False
            for item in inline_items:
                if int(item.get("index") or 0) not in existing_indices:
                    plan.append(item)
                    changed = True
                else:
                    # Overwrite with the freshly-pasted version
                    plan = [
                        item if int(r.get("index") or 0) == int(item.get("index") or 0) else r
                        for r in plan
                    ]
                    changed = True
            if changed:
                ensure_broll_plan(memory, plan)
                save_production_memory(tenant_id, memory)

        if not plan:
            return {
                "assistant_message": (
                    "No IMAGE 1 / IMAGE 2 / … blocks found in your brief. "
                    "Add B-roll image sections with timing and prompts, then retry."
                ),
                "intent": "reply",
                "phase": "planning",
                "suggested_actions": ["generate_image"],
                "status": "failed",
                "error": "broll_plan_missing",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
            }
        pending = pending_broll_indices(memory)
        # If inline paste specifies an index, use it; otherwise pick first pending
        inline_idx = int(inline_items[0]["index"]) if inline_items else 0
        idx = inline_idx or int(broll_index or 0) or (pending[0] if pending else int(plan[0]["index"]))
        item = next((row for row in plan if int(row["index"]) == idx), None)
        if not item:
            return {
                "assistant_message": f"B-roll IMAGE {idx} is not defined in the brief.",
                "intent": "reply",
                "phase": "awaiting_broll",
                "suggested_actions": ["generate_broll_image"],
                "status": "failed",
                "error": "broll_not_found",
                "job_id": None,
                "media_mode": None,
                "model": None,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
            }
        broll_prompt = str(item.get("image_prompt") or "").strip()
        job_id = await _start_job(
            tenant_id=tenant_id,
            media_mode="image",
            model=img_model,
            prompt=broll_prompt,
            duration_seconds=out_duration,
            aspect=out_aspect,
            resolution=resolution,
            sound_on=False,
            seed_image_url=None,
            product_name=product_name,
            brand_name=brand_name,
            product_reference_url=None,
            logo_reference_url=logo_ref or None,
            additional_reference_urls=extra_refs,
            reference_assets=reference_assets,
            preserve_image_text=bool(item.get("wants_readable_text", True)),
            session_id=session_id,
            broll_index=idx,
            broll_title=str(item.get("title") or f"B-roll {idx}"),
        )
        readable = bool(item.get("wants_readable_text", True))
        regen = action_norm == "regenerate_broll_image"
        return {
            "assistant_message": (
                f"{'Regenerating' if regen else 'Generating'} B-roll IMAGE {idx}: {item.get('title')}. "
                + (
                    "Review that every label, number and headline is spelled correctly and sharp — "
                    "then Approve B-roll. Seedance will animate this exact PNG without redrawing text."
                    if readable
                    else "Review for clean visuals and no gibberish, then Approve B-roll. "
                    "Seedance will animate this exact PNG without redrawing the scene."
                )
            ),
            "intent": "generate_image",
            "phase": "broll_running",
            "suggested_actions": [],
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": active_video_model,
            "image_prompt": broll_prompt,
            "broll_index": idx,
            "status": "queued",
            "job_id": job_id,
            "media_mode": "image",
            "model": img_model,
            "duration_seconds": out_duration,
            "aspect": out_aspect,
            "error": None,
        }

    if action_norm in {"generate_image", "regenerate_image", "generate_storyboard"}:
        prompt = (image_prompt or "").strip()
        notes = (revision_notes or last_user or "").strip()
        clone_character_urls = [
            str(asset.get("url") or "").strip()
            for asset in (reference_assets or [])
            if isinstance(asset, dict)
            and str(asset.get("role") or "").strip().lower() == "character"
            and str(asset.get("url") or "").strip()
        ]
        clone_character_urls = list(dict.fromkeys(clone_character_urls))[:8]
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
        if clone_mode:
            from app.services.creative_studio_clone import compile_clone_prompt

            clone_direction = prompt or last_user
            if re.fullmatch(r"\((?:generate|regenerate)[ _]image\)", clone_direction, re.I):
                clone_direction = ""
            prompt = compile_clone_prompt(
                user_prompt=clone_direction,
                scene_id=clone_scene_id,
                clone_count=clone_count,
            )
        prompt = _with_product_fidelity(prompt, product_ref or None)
        if not prompt:
            return {
                "assistant_message": "I need an image prompt first — describe the still / background scene.",
                "intent": "reply",
                "phase": "planning",
                "suggested_actions": [],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": active_video_model,
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

        if not _image_generation_configured():
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
                "video_model": active_video_model,
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
            chapter_still_prompt,
            chapter_still_prompt_from_brief,
            looks_like_multi_scene_brief,
            opening_still_prompt,
        )

        brief = full_brief
        scenes = [] if clone_mode else _scenes_from_llm_or_brief(None, brief, product_name=product_name or "product")
        # Also try parsing image_prompt if it embeds Scene markers
        if not clone_mode and len(scenes) < 2 and looks_like_multi_scene_brief(prompt):
            scenes = _scenes_from_llm_or_brief(None, prompt, product_name=product_name or "product")

        continuity_url = (continuity_style_url or "").strip()
        if chapter_staging:
            from app.services.creative_studio_broll import broll_items_for_chapter
            from app.services.creative_studio_production_memory import (
                approved_broll_urls,
                pending_broll_indices,
            )

            memory = _ensure_broll_memory()
            plan = list(memory.get("broll_plan") or [])
            shots = list(memory.get("shot_list") or [])
            if (
                plan
                and shots
                and active_chapter_index < len(shots)
                and action_norm == "generate_image"
                and not next_chapter_image
            ):
                shot = shots[active_chapter_index]
                chapter_brolls = broll_items_for_chapter(
                    plan,
                    chapter_start=float(shot["start"]),
                    chapter_end=float(shot["end"]),
                )
                approved = approved_broll_urls(memory)
                missing = [
                    int(item["index"])
                    for item in chapter_brolls
                    if int(item["index"]) not in approved
                ]
                if missing:
                    return {
                        "assistant_message": (
                            f"Generate and approve B-roll stills for this chapter first "
                            f"(IMAGE {missing[0]}…{missing[-1]}). GPT Image 2 renders readable "
                            "text correctly; Seedance animates the approved PNG without redrawing it."
                        ),
                        "intent": "reply",
                        "phase": "awaiting_broll",
                        "suggested_actions": ["generate_all_broll", "generate_broll_image"],
                        "chat_model": model_slug,
                        "image_model": img_model,
                        "video_model": active_video_model,
                        "broll_index": missing[0],
                        "status": "ok",
                        "job_id": None,
                        "media_mode": None,
                        "model": None,
                        "duration_seconds": out_duration,
                        "aspect": out_aspect,
                        "error": None,
                    }
                if chapter_brolls and action_norm == "generate_image" and not next_chapter_image:
                    return {
                        "assistant_message": (
                            f"Chapter {active_chapter_index + 1} B-roll stills are approved. "
                            f"{_seedance_presenter_note()}"
                        ),
                        "intent": "reply",
                        "phase": "awaiting_video",
                        "suggested_actions": ["approve_next"],
                        "chat_model": model_slug,
                        "image_model": img_model,
                        "video_model": active_video_model,
                        "video_prompt": video_prompt or None,
                        "status": "ok",
                        "job_id": None,
                        "media_mode": None,
                        "model": None,
                        "duration_seconds": out_duration,
                        "aspect": out_aspect,
                        "error": None,
                    }
            if next_chapter_image and not continuity_url:
                return {
                    "assistant_message": (
                        "The previous chapter's continuity frame is missing. "
                        "Review the last video part first, then generate the next chapter still."
                    ),
                    "intent": "reply",
                    "phase": "awaiting_chapter_image",
                    "suggested_actions": [],
                    "chat_model": model_slug,
                    "image_model": img_model,
                    "video_model": active_video_model,
                    "image_prompt": image_prompt or None,
                    "video_prompt": video_prompt or None,
                    "approved_image_url": approved_image_url or None,
                    "product_reference_url": product_ref or None,
                    "status": "failed",
                    "error": "continuity_frame_missing",
                    "job_id": None,
                    "media_mode": None,
                    "model": None,
                    "duration_seconds": out_duration,
                    "aspect": out_aspect,
                    "chapter_index": active_chapter_index,
                    "film_total_chapters": film_chapters,
                }
            chapter_prompt = (
                chapter_still_prompt_from_brief(
                    brief,
                    active_chapter_index,
                    from_continuity=bool(continuity_url),
                )
                or chapter_still_prompt(
                    scenes,
                    active_chapter_index,
                    from_continuity=bool(continuity_url),
                )
                or prompt
            )
            chapter_prompt = _with_product_fidelity(chapter_prompt, product_ref or None)
            vid = (video_prompt or "").strip() or build_storyboard_video_prompt(
                scenes,
                duration_seconds=out_duration,
                sound_on=sound_on,
                product_name=product_name or "",
            )
            job_id = await _start_job(
                tenant_id=tenant_id,
                media_mode="image",
                model=img_model,
                prompt=chapter_prompt,
                duration_seconds=out_duration,
                aspect=out_aspect,
                resolution=resolution,
                sound_on=False,
                seed_image_url=None,
                product_name=product_name,
                brand_name=brand_name,
                product_reference_url=product_ref or None,
                logo_reference_url=logo_ref or None,
                additional_reference_urls=extra_refs,
                reference_assets=reference_assets,
                preserve_image_text=preserve_image_text,
                session_id=session_id,
                chapter_image_staging=True,
                film_chapter_index=active_chapter_index,
                film_total_chapters=film_chapters,
                full_film_duration=out_duration,
                continuity_style_url=continuity_url or None,
            )
            chapter_num = active_chapter_index + 1
            return {
                "assistant_message": (
                    f"Generating GPT Image 2 opening still for chapter {chapter_num}/{film_chapters}. "
                    + (
                        "Using the previous chapter's final frame for cast and scene continuity. "
                        if continuity_url
                        else ""
                    )
                    + "Review it, then Approve & Next — that exact PNG becomes Seedance first_frame "
                    "for this 15s chapter (nothing else is used as the opening)."
                ),
                "intent": "generate_image",
                "phase": "image_running",
                "suggested_actions": [],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": active_video_model,
                "image_prompt": chapter_prompt,
                "video_prompt": vid,
                "approved_image_url": None,
                "product_reference_url": product_ref or None,
                "status": "queued",
                "job_id": job_id,
                "media_mode": "image",
                "model": img_model,
                "duration_seconds": out_duration,
                "aspect": out_aspect,
                "chapter_index": active_chapter_index,
                "film_total_chapters": film_chapters,
                "error": None,
            }

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
                preserve_image_text=preserve_image_text,
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
                "video_model": active_video_model,
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
            logo_reference_url=logo_ref or None,
            additional_reference_urls=extra_refs,
            reference_assets=reference_assets,
            preserve_image_text=preserve_image_text,
            clone_mode=clone_mode,
            clone_scene_id=clone_scene_id,
            clone_count=clone_count,
            clone_identity_prompt=clone_direction if clone_mode else "",
            background_only_image=bool(
                not clone_mode
                and clone_character_urls
                and re.search(
                    r"(?i)\b(?:b-?roll|supporting background|background image)\b",
                    full_brief,
                )
            ),
        )
        verb = "Regenerating" if action_norm == "regenerate_image" else "Generating"
        ref_note = (
            f" Creating {clone_count} copies of the character in one scene."
            if clone_mode
            else
            " Matching your attached product photo."
            if product_ref
            else ""
        )
        return {
            "assistant_message": (
                f"{verb} {'clone image' if clone_mode else 'background still'} with GPT Image 2.{ref_note} "
                + (
                    "If no Character photo is selected, GPT Image 2 will first create and save one reusable identity portrait, then use it for the clone scene."
                    if clone_mode
                    else "When it lands, review it — Regenerate with notes, or Approve & Next to animate with Seedance 2.0."
                )
            ),
            "intent": "generate_image",
            "phase": "image_running",
            "suggested_actions": [],
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": active_video_model,
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
        from app.services.creative_studio_broll import (
            is_production_setup_only_message,
            parse_broll_images,
        )
        from app.services.creative_studio_production_memory import (
            approved_broll_urls,
            pending_broll_indices,
        )

        if is_production_setup_only_message(last_user):
            return _production_lock_reply()

        broll_plan = parse_broll_images(full_brief)
        if broll_plan:
            memory = _ensure_broll_memory()
            approved = approved_broll_urls(memory)
            pending = pending_broll_indices(memory)
            if pending or len(approved) < len(broll_plan):
                return {
                    "assistant_message": (
                        f"B-roll stills must be approved before Seedance ({len(approved)}/{len(broll_plan)} done). "
                        "Generate each IMAGE still, review, and Approve B-roll — then start chapter 1."
                    ),
                    "intent": "reply",
                    "phase": "awaiting_broll",
                    "suggested_actions": ["generate_all_broll", "generate_broll_image"],
                    "chat_model": model_slug,
                    "image_model": img_model,
                    "video_model": active_video_model,
                    "broll_index": pending[0] if pending else int(broll_plan[0]["index"]),
                    "status": "ok",
                    "job_id": None,
                    "media_mode": None,
                    "model": None,
                    "duration_seconds": out_duration,
                    "aspect": out_aspect,
                    "error": None,
                }

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
                "video_model": active_video_model,
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
        broll_video_ready = False
        approved_broll_for_video: list[str] = []
        if session_id:
            from app.services.creative_studio_production_memory import (
                approved_broll_urls,
                pending_broll_indices,
            )

            try:
                broll_memory = _ensure_broll_memory()
                approved_map = approved_broll_urls(broll_memory)
                approved_broll_for_video = [
                    approved_map[index] for index in sorted(approved_map)
                ][:9]
                broll_video_ready = (
                    bool(broll_memory.get("broll_plan"))
                    and bool(approved_broll_for_video)
                    and not pending_broll_indices(broll_memory)
                )
            except Exception:
                broll_video_ready = False

        if not seed and not prompt_only_video and not broll_video_ready:
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
                "video_model": active_video_model,
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
        gemini_selected = is_gemini_omni_model(active_video_model)
        provider_configured = (
            gemini_omni_configured()
            if gemini_selected
            else ark_configured_for_model(active_video_model)
        )
        if not provider_configured:
            return {
                "assistant_message": (
                    "Gemini Omni isn’t configured — set GEMINI_API_KEY in backend .env."
                    if gemini_selected
                    else "Seedance isn’t configured — set ARK_API_KEY (2.0) and/or "
                    "ARK_API_KEY_25 (2.5) in backend .env."
                ),
                "intent": "reply",
                "phase": "awaiting_video",
                "suggested_actions": ["approve_next"],
                "chat_model": model_slug,
                "image_model": img_model,
                "video_model": active_video_model,
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
                from app.services.creative_studio_timeline import (
                    explicit_shot_windows,
                    normalize_video_timeline_prompt,
                )

                try:
                    authored_windows = explicit_shot_windows(brief_for_motion)
                    if authored_windows:
                        out_duration = max(
                            5, min(120, int(round(authored_windows[-1][1])))
                        )
                    motion = normalize_video_timeline_prompt(
                        brief_for_motion,
                        brief_for_motion,
                        total=float(out_duration),
                    )
                    if not explicit_shot_windows(motion, total=out_duration):
                        motion = build_storyboard_video_prompt(
                            board,
                            duration_seconds=out_duration,
                            sound_on=sound_on,
                            product_name=product_name or "",
                        )
                except ValueError:
                    motion = normalize_video_timeline_prompt(
                        brief_for_motion,
                        brief_for_motion,
                        total=float(out_duration),
                    )

        if len(brief_for_motion) < 80:
            brief_for_motion = f"{image_prompt}\n{video_prompt}\n{last_user}".strip()

        # A generated B-roll still prompt describes only one supporting image.
        # It must never replace the original full-film brief when the user
        # approves the B-roll board for video generation.
        if broll_video_ready and brief_for_motion:
            motion = brief_for_motion

        if prompt_only_video:
            # Direct mode preserves the user's authored timed prompt verbatim.
            # For master production briefs, trim the prompt to only the scenes that
            # fall within the current chapter's time window — this stops Seedance from
            # receiving 75s of dialogue in one call (causes 8s clip + multiple voices).
            if _is_master_brief or is_master_production_brief(brief_for_motion):
                from app.services.creative_studio_broll import parse_scene_plan
                from app.services.creative_studio_production_memory import load_production_memory

                mem = load_production_memory(tenant_id, session_id or "draft") or {}
                scene_plan_all = mem.get("scene_plan") or parse_scene_plan(brief_for_motion)
                if scene_plan_all:
                    # Work out the chapter time window from the shot_list
                    shot_list = list(mem.get("shot_list") or [])
                    if shot_list and active_chapter_index < len(shot_list):
                        ch = shot_list[active_chapter_index]
                        ch_start = float(ch.get("start") or 0)
                        ch_end = float(ch.get("end") or out_duration)
                    else:
                        ch_start, ch_end = 0.0, float(out_duration)

                    # Collect only the scenes that overlap this chapter window
                    chapter_scenes = [
                        s for s in scene_plan_all
                        if float(s.get("end", 0)) > ch_start - 0.5
                        and float(s.get("start", 0)) < ch_end + 0.5
                    ]

                    if chapter_scenes:
                        lines = [
                            "ONE FICTIONAL PRESENTER — SINGLE VOICE — NATURAL PACE — "
                            "LIP-SYNC EVERY WORD EXACTLY AS WRITTEN. NO SECOND VOICE.\n"
                        ]
                        for sc in chapter_scenes:
                            m_s, s_s = divmod(int(sc.get("start", 0)), 60)
                            m_e, s_e = divmod(int(sc.get("end", 0)), 60)
                            t_label = f"{m_s:02d}:{s_s:02d}–{m_e:02d}:{s_e:02d}"
                            sc_type = str(sc.get("type", "presenter")).upper()
                            dialogue = str(sc.get("dialogue") or "").strip()
                            visual = str(sc.get("visual") or "").strip()
                            if dialogue:
                                lines.append(
                                    f"[{t_label} — {sc_type}]\n"
                                    f"SPEAK EXACTLY: \"{dialogue}\"\n"
                                    f"VISUAL: {visual}"
                                )
                        motion = "\n\n".join(lines)
                    else:
                        motion = brief_for_motion or motion
                else:
                    motion = brief_for_motion or motion
            else:
                # Direct mode preserves the user's authored timed prompt verbatim.
                motion = brief_for_motion or motion
        else:
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

        continuity_for_job = (continuity_style_url or "").strip()
        staged_paths = list(accumulated_segment_paths or [])
        if chapter_staging and session_id and action_norm in {"approve_next", "generate_video"}:
            from app.services.creative_studio_production_memory import load_production_memory

            memory = load_production_memory(tenant_id, session_id) or {}
            chapter_log = list(memory.get("chapter_log") or [])
            if chapter_log:
                if active_chapter_index < len(chapter_log):
                    active_chapter_index = len(chapter_log)
                if not continuity_for_job:
                    continuity_for_job = str(
                        chapter_log[-1].get("continuity_frame_url") or ""
                    ).strip()
                if not staged_paths:
                    staged_paths = [
                        str(item.get("video_path") or "").strip()
                        for item in chapter_log
                        if str(item.get("video_path") or "").strip()
                    ]

        multi_beat = bool(
            re.search(r"(?i)\bCLIP\s*2\b|\bHOOK\b|\bBODY\b|\bScene\s*2\b", motion)
        ) or looks_like_multi_scene_brief(motion)
        chapter_video_duration = out_duration
        chapter_motion = motion
        if chapter_staging:
            from app.services.creative_studio_production_memory import (
                compile_locked_chapter_prompt,
                ensure_production_memory,
                normalized_reference_lock,
            )
            from app.services.creative_studio_video_finishing import extract_voiceover_events

            chapter_video_duration = _chapter_duration(
                out_duration, clip_cap, active_chapter_index
            )
            voice_events = extract_voiceover_events(motion or full_brief)
            refs = normalized_reference_lock(
                list(reference_assets or []),
                product_reference_url=product_ref or None,
                logo_reference_url=logo_ref or None,
            )
            memory = ensure_production_memory(
                tenant_id=tenant_id,
                session_id=session_id,
                prompt=motion,
                duration_seconds=out_duration,
                clip_cap=clip_cap,
                aspect=out_aspect,
                resolution=resolution or "1080p",
                model=active_video_model,
                brand_name=brand_name,
                product_name=product_name,
                voice_events=voice_events,
                references=refs,
                storyboard_count=1,
            )
            locked_shots = list(memory.get("shot_list") or [])
            if locked_shots:
                film_chapters = len(locked_shots)
                chapter_video_duration = _locked_chapter_duration(
                    memory,
                    active_chapter_index,
                    fallback=chapter_video_duration,
                )
            chapter_motion = compile_locked_chapter_prompt(
                memory,
                chapter_index=active_chapter_index,
                speech_mode=speech_mode,
            )
        broll_segments: list[dict[str, Any]] = []
        if chapter_staging and session_id:
            from app.services.creative_studio_broll import (
                broll_items_for_chapter,
                build_chapter_broll_segments,
            )
            from app.services.creative_studio_production_memory import (
                approved_broll_seedance_urls,
                approved_broll_urls,
                ensure_broll_plan,
            )

            memory = _ensure_broll_memory()
            ensure_broll_plan(memory, list(memory.get("broll_plan") or []))
            plan = list(memory.get("broll_plan") or [])
            shots = list(memory.get("shot_list") or [])
            if active_chapter_index < len(shots):
                shot = shots[active_chapter_index]
                chapter_start = float(shot["start"])
                chapter_end = float(shot["end"])
                chapter_brolls = broll_items_for_chapter(
                    plan, chapter_start=chapter_start, chapter_end=chapter_end
                )
                approved = approved_broll_urls(memory)
                approved_for_seedance = approved_broll_seedance_urls(memory)
                missing = [
                    int(item["index"])
                    for item in chapter_brolls
                    if int(item["index"]) not in approved
                ]
                if missing:
                    return {
                        "assistant_message": (
                            f"Chapter {active_chapter_index + 1} still needs approved B-roll "
                            f"still(s) IMAGE {missing[0]}"
                            + (f"–{missing[-1]}" if len(missing) > 1 else "")
                            + " before Seedance video. Generate and Approve B-roll for each."
                        ),
                        "intent": "reply",
                        "phase": "awaiting_broll",
                        "suggested_actions": ["generate_all_broll", "generate_broll_image"],
                        "broll_index": missing[0],
                        "status": "failed",
                        "error": "chapter_broll_missing",
                        "job_id": None,
                        "media_mode": None,
                        "model": None,
                        "duration_seconds": out_duration,
                        "aspect": out_aspect,
                    }
                proof_url = _proof_still_url()
                built = build_chapter_broll_segments(
                    chapter_index=active_chapter_index,
                    chapter_start=chapter_start,
                    chapter_end=chapter_end,
                    # Presenter briefs intentionally leave this empty so Seedance
                    # creates the fictional presenter. Product-only briefs use the
                    # uploaded authoritative product/approved still for every gap.
                    opening_still_url=(product_ref or seed or ""),
                    proof_still_url=proof_url,
                    broll_plan=plan,
                    approved_broll=approved_for_seedance,
                    chapter_motion_prompt=chapter_motion,
                )
                if chapter_brolls and not any(
                    str(seg.get("kind") or "") == "broll" for seg in built
                ):
                    return {
                        "assistant_message": (
                            "Approved B-roll stills were not found in production memory. "
                            "Re-approve each IMAGE still (Approve B-roll), then try Seedance again."
                        ),
                        "intent": "reply",
                        "phase": "awaiting_broll",
                        "suggested_actions": ["generate_all_broll", "generate_broll_image"],
                        "status": "failed",
                        "error": "approved_broll_lost",
                        "job_id": None,
                        "media_mode": None,
                        "model": None,
                        "duration_seconds": out_duration,
                        "aspect": out_aspect,
                    }
                if any(
                    str(seg.get("kind") or "") in {"broll", "product"}
                    for seg in built
                ):
                    broll_segments = built
        job_id = await _start_job(
            tenant_id=tenant_id,
            media_mode="video",
            model=active_video_model,
            prompt=chapter_motion,
            duration_seconds=chapter_video_duration if chapter_staging else out_duration,
            aspect=out_aspect,
            resolution=resolution,
            sound_on=sound_on,
            speech_mode=speech_mode,
            seed_image_url=(
                None
                if (prompt_only_video and not is_gemini_omni_model(active_video_model))
                or broll_segments
                else (selected_character_url or seed or None)
                if is_gemini_omni_model(active_video_model)
                else seed or None
            ),
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
            storyboard_image_urls=(
                []
                if prompt_only_video or broll_segments
                else approved_broll_for_video
                if broll_video_ready
                else [u for u in (storyboard_image_urls or []) if (u or "").strip()][:9]
                if not chapter_staging
                else ([seed] if seed and not broll_segments else [])
            ),
            require_storyboard_coverage=not broll_video_ready,
            prompt_only_video=prompt_only_video,
            session_id=session_id,
            chapter_image_staging=chapter_staging,
            film_chapter_index=active_chapter_index,
            film_total_chapters=film_chapters,
            full_film_duration=out_duration,
            accumulated_segment_paths=staged_paths,
            broll_segments=broll_segments,
            continuity_style_url=continuity_for_job or None,
        )
        audio_note = (
            "with native presenter speech"
            if sound_on and speech_mode == "native_presenter"
            else "with exact studio voiceover"
            if sound_on
            else "silent"
        )
        chapter_note = ""
        if chapter_staging:
            broll_note = (
                f" {len(broll_segments)} segment(s): B-roll dashboards use approved stills; "
                "presenter beats are text-to-video (no photoreal face still)."
                if broll_segments
                else ""
            )
            chapter_note = (
                f" Chapter {active_chapter_index + 1}/{film_chapters} "
                f"({chapter_video_duration}s).{broll_note} After review, continue to the next chapter."
            )
            if active_chapter_index > 0 and continuity_for_job:
                chapter_note += (
                    " Presenter continuity uses chapter "
                    f"{active_chapter_index}'s final frame."
                )
        return {
            "assistant_message": (
                f"Approved. Queuing {video_model_label} · "
                f"{chapter_video_duration if chapter_staging else out_duration}s · "
                f"{out_aspect.replace('/', ':')} · {audio_note}. "
                + (
                    f"Driving chapter {active_chapter_index + 1}/{film_chapters} from your "
                    + (
                        "approved B-roll stills + script-driven presenter (text-to-video)."
                        if broll_segments
                        else "approved still."
                    )
                    if chapter_staging
                    else "Driving the FULL timed story from your brief"
                    + (
                        " as direct Seedance chapters using uploaded references as general visual "
                        "guidance while generating a fictional character; no GPT-generated storyboard images."
                        if prompt_only_video
                        else (
                            " using the approved B-roll references and selected Character in one "
                            "Seedance 2.5 call."
                            if broll_video_ready and not seed
                            else " (approved still as opening frame, then progressing through each beat)."
                        )
                    )
                )
                + chapter_note
                + (
                    " Product photo fidelity kept in the motion brief."
                    if product_ref else ""
                )
            ),
            "intent": "generate_video",
            "phase": "video_running",
            "suggested_actions": [],
            "chat_model": model_slug,
            "image_model": img_model,
            "video_model": active_video_model,
            "image_prompt": image_prompt or None,
            "video_prompt": motion,
            "approved_image_url": None if prompt_only_video else seed or None,
            "product_reference_url": product_ref or None,
            "status": "queued",
            "job_id": job_id,
            "media_mode": "video",
            "model": active_video_model,
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
            "video_model": active_video_model,
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
            speech_mode=speech_mode,
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
            prompt_only_video=prompt_only_video,
            preserve_image_text=preserve_image_text,
            video_model=active_video_model,
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
            speech_mode=speech_mode,
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
            prompt_only_video=prompt_only_video,
            preserve_image_text=preserve_image_text,
            video_model=active_video_model,
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
                f"{video_model_label} playing the timed story beats."
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
                speech_mode=speech_mode,
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
                prompt_only_video=prompt_only_video,
                preserve_image_text=preserve_image_text,
                video_model=active_video_model,
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
            "video_model": active_video_model,
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
        "video_model": active_video_model,
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
