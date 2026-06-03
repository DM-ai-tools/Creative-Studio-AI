"""Higgsfield platform model paths (https://platform.higgsfield.ai) mapped to CLI catalog ids."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class HiggsfieldModelSpec:
    job_set_type: str
    label: str
    platform_path: str
    modality: str  # image | video
    requires_image: bool = False
    api_style: str = "platform"  # platform | v1_dop | v1_soul


# Image models (18) — paths verified via platform API where noted
HIGGSFIELD_IMAGE_SPECS: list[HiggsfieldModelSpec] = [
    HiggsfieldModelSpec("nano_banana_2", "Nano Banana Pro", "reve/text-to-image", "image"),
    HiggsfieldModelSpec("nano_banana_flash", "Nano Banana 2", "reve/text-to-image", "image"),
    HiggsfieldModelSpec("nano_banana", "Nano Banana", "reve/text-to-image", "image"),
    HiggsfieldModelSpec("flux_2", "FLUX.2", "flux-2", "image"),
    HiggsfieldModelSpec(
        "flux_kontext",
        "Flux Kontext",
        "flux-pro/kontext/max/text-to-image",
        "image",
    ),
    HiggsfieldModelSpec(
        "gpt_image_2",
        "GPT Image 2",
        "flux-pro/kontext/max/text-to-image",
        "image",
    ),
    HiggsfieldModelSpec(
        "text2image_soul_v2",
        "Higgsfield Soul V2",
        "higgsfield-ai/soul/v2/standard",
        "image",
    ),
    HiggsfieldModelSpec(
        "seedream_v4_5",
        "Seedream 4.5",
        "bytedance/seedream/v4/text-to-image",
        "image",
    ),
    HiggsfieldModelSpec(
        "seedream_v5_lite",
        "Seedream V5 Lite",
        "bytedance/seedream/v5-lite/text-to-image",
        "image",
    ),
    HiggsfieldModelSpec("grok_image", "Grok Image", "reve/text-to-image", "image"),
    HiggsfieldModelSpec("openai_hazel", "OpenAI Hazel", "reve/text-to-image", "image"),
    HiggsfieldModelSpec("image_auto", "Image Auto", "reve/text-to-image", "image"),
    HiggsfieldModelSpec("z_image", "Z Image", "reve/text-to-image", "image"),
    HiggsfieldModelSpec("kling_omni_image", "Kling O1 Image", "reve/text-to-image", "image"),
    HiggsfieldModelSpec(
        "cinematic_studio_2_5",
        "Cinematic Studio 2.5",
        "higgsfield-ai/soul/standard",
        "image",
    ),
    HiggsfieldModelSpec(
        "soul_cinematic",
        "Soul Cinematic",
        "higgsfield-ai/soul/standard",
        "image",
    ),
    HiggsfieldModelSpec(
        "soul_location",
        "Soul Location",
        "higgsfield-ai/soul/standard",
        "image",
    ),
    HiggsfieldModelSpec(
        "marketing_studio_image",
        "Marketing Studio Image",
        "marketing-studio-image",
        "image",
    ),
]

# Video models (16) — excludes brain_activity (analysis-only)
HIGGSFIELD_VIDEO_SPECS: list[HiggsfieldModelSpec] = [
    HiggsfieldModelSpec(
        "veo3_1",
        "Google Veo 3.1",
        "higgsfield-ai/dop/standard",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "veo3_1_lite",
        "Google Veo 3.1 Lite",
        "higgsfield-ai/dop/lite",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "veo3",
        "Google Veo 3",
        "higgsfield-ai/dop/standard",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "kling3_0",
        "Kling v3.0",
        "kling-video/v3.0/pro/image-to-video",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "kling2_6",
        "Kling 2.6 Video",
        "kling-video/v2.1/pro/image-to-video",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "seedance_2_0",
        "Seedance 2.0",
        "higgsfield-ai/dop/turbo",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "seedance1_5",
        "Seedance 1.5 Pro",
        "higgsfield-ai/dop/standard",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "wan2_7",
        "Wan 2.7",
        "higgsfield-ai/dop/standard",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "wan2_6",
        "Wan 2.6 Video",
        "higgsfield-ai/dop/standard",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "minimax_hailuo",
        "Minimax Hailuo",
        "higgsfield-ai/dop/standard",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "grok_video",
        "Grok Video",
        "higgsfield-ai/dop/turbo",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "cinematic_studio_3_0",
        "Cinematic Studio 3.0",
        "higgsfield-ai/dop/standard",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "cinematic_studio_video",
        "Cinematic Studio Video",
        "higgsfield-ai/dop/standard",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "cinematic_studio_video_v2",
        "Cinematic Studio Video V2",
        "higgsfield-ai/dop/turbo",
        "video",
        requires_image=True,
    ),
    HiggsfieldModelSpec(
        "soul_cast",
        "Soul Cast",
        "higgsfield-ai/soul/v2/standard",
        "video",
    ),
    HiggsfieldModelSpec(
        "marketing_studio_video",
        "Marketing Studio Video",
        "marketing-studio-video",
        "video",
        requires_image=True,
    ),
]

_IMAGE_BY_CATALOG: dict[str, HiggsfieldModelSpec] = {}
_VIDEO_BY_CATALOG: dict[str, HiggsfieldModelSpec] = {}


def _register_spec(store: dict[str, HiggsfieldModelSpec], spec: HiggsfieldModelSpec) -> None:
    store[f"hf-{spec.job_set_type.replace('_', '-')}"] = spec
    store[spec.job_set_type] = spec
    store[f"hf-{spec.job_set_type}"] = spec


for _spec in HIGGSFIELD_IMAGE_SPECS:
    _register_spec(_IMAGE_BY_CATALOG, _spec)
for _spec in HIGGSFIELD_VIDEO_SPECS:
    _register_spec(_VIDEO_BY_CATALOG, _spec)


def higgsfield_configured() -> bool:
    return bool(
        (settings.HIGGSFIELD_API_KEY or "").strip()
        and (settings.HIGGSFIELD_API_SECRET or "").strip()
    )


def is_higgsfield_image_model(model: str | None) -> bool:
    key = _normalize_catalog_id(model)
    return key.startswith("hf-") or key in _IMAGE_BY_CATALOG


def is_higgsfield_video_model(model: str | None) -> bool:
    key = _normalize_catalog_id(model)
    if key.startswith("hf-"):
        return True
    return key in _VIDEO_BY_CATALOG


def resolve_image_spec(catalog_id: str | None) -> HiggsfieldModelSpec | None:
    key = _normalize_catalog_id(catalog_id)
    return _IMAGE_BY_CATALOG.get(key)


def resolve_video_spec(catalog_id: str | None) -> HiggsfieldModelSpec | None:
    key = _normalize_catalog_id(catalog_id)
    return _VIDEO_BY_CATALOG.get(key)


def _normalize_catalog_id(catalog_id: str | None) -> str:
    raw = (catalog_id or "").strip().lower()
    if raw.startswith("higgsfield-"):
        return "hf-" + raw.removeprefix("higgsfield-")
    return raw


def aspect_ratio_for_format(format_type: str) -> str:
    ft = (format_type or "").lower()
    if ft in {"reel", "video", "stories"}:
        return "9:16"
    if ft == "carousel":
        return "16:9"
    return "1:1"


def build_image_arguments(*, prompt: str, format_type: str) -> dict:
    return {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio_for_format(format_type),
        "resolution": "1k",
    }


def resolve_higgsfield_video_duration(
    job_set_type: str, requested: int
) -> tuple[int, str | None]:
    """
    Map UI duration to what each Higgsfield model accepts.
    Returns (api_seconds, warning_or_none).
    """
    req = max(2, int(requested or 5))
    job = (job_set_type or "").lower()

    if job.startswith("kling"):
        allowed = (5, 10)
        api = min(allowed, key=lambda x: abs(x - req))
        warn = None
        if req > 10:
            warn = f"Kling supports up to 10s; using {api}s (you asked for {req}s)."
        return api, warn

    if job in ("minimax_hailuo",):
        allowed = (6, 10)
        api = min(allowed, key=lambda x: abs(x - req))
        if req > 10:
            return api, f"Minimax Hailuo max 10s; using {api}s."
        return api, None

    if job in ("seedance1_5",):
        allowed = (4, 8, 12)
        api = min(allowed, key=lambda x: abs(x - req))
        if req > 12:
            return api, f"Seedance 1.5 max 12s; using {api}s."
        return api, None

    if job in ("seedance_2_0",):
        api = max(2, min(15, req))
        if req > 15:
            return 15, f"Seedance 2.0 max ~15s; using 15s (you asked for {req}s)."
        return api, None

    if job == "marketing_studio_video":
        api = max(5, min(30, req))
        if req > 30:
            return 30, f"Marketing Studio max 30s; using 30s."
        return api, None

    if job in ("cinematic_studio_video", "cinematic_studio_video_v2", "cinematic_studio_3_0"):
        allowed = (5, 10)
        api = min(allowed, key=lambda x: abs(x - req))
        if req > 10:
            return api, f"Cinematic Studio max 10s; using {api}s."
        return api, None

    # DoP / Veo-labeled paths (higgsfield-ai/dop/*) — typically 5s per clip
    if job.startswith("veo") or "dop" in job:
        api = 5
        if req > 5:
            return api, (
                f"This Higgsfield clip is limited to 5s. For longer ads pick "
                f"Kling v3.0 or Marketing Studio Video (you asked for {req}s)."
            )
        return api, None

    api = max(2, min(15, req))
    return api, None


def higgsfield_supports_native_audio(job_set_type: str) -> bool:
    """
    Only models whose platform payload actually enables audio generation.
    DoP/Veo/Wan paths do NOT include audio — those need Runway TTS voiceover.
    """
    job = (job_set_type or "").lower()
    return job.startswith("kling") or job == "marketing_studio_video"


def _append_spoken_dialogue_to_prompt(prompt: str, spoken_script: str | None) -> str:
    """Give audio-capable models explicit dialogue (improves native speech sync)."""
    spoken = " ".join((spoken_script or "").split())
    if not spoken or len(spoken) < 12:
        return prompt
    snippet = spoken if len(spoken) <= 480 else spoken[:477].rsplit(" ", 1)[0] + "."
    return (
        f"{prompt.rstrip()}\n\n"
        f"Natural spoken voiceover (clear Australian English, no on-screen text): {snippet}"
    )


def build_video_arguments(
    *,
    prompt: str,
    format_type: str,
    duration: int,
    image_url: str | None,
    spec: HiggsfieldModelSpec,
    spoken_script: str | None = None,
) -> dict:
    ratio = aspect_ratio_for_format(format_type)
    api_duration, _warn = resolve_higgsfield_video_duration(spec.job_set_type, duration)
    path = spec.platform_path

    if path.startswith("/v1/image2video/dop"):
        model_slug = "turbo" if "turbo" in spec.job_set_type else "standard"
        if "lite" in spec.job_set_type:
            model_slug = "lite"
        return {
            "model": f"dop-{model_slug}",
            "prompt": prompt,
            "input_images": [{"type": "image_url", "image_url": image_url}],
        }

    if "dop/" in path or path.startswith("higgsfield-ai/dop"):
        payload: dict = {
            "prompt": prompt,
            "duration": api_duration,
            "aspect_ratio": ratio,
        }
        if image_url:
            payload["image_url"] = image_url
        return payload

    if path.startswith("kling-video"):
        payload = {
            "prompt": _append_spoken_dialogue_to_prompt(prompt, spoken_script),
            "aspect_ratio": ratio,
            "duration": api_duration,
            "sound": "on",
        }
        if image_url:
            payload["image_url"] = image_url
        return payload

    if spec.job_set_type == "marketing_studio_video":
        payload = {
            "prompt": _append_spoken_dialogue_to_prompt(prompt, spoken_script),
            "aspect_ratio": ratio,
            "duration": api_duration,
            "generate_audio": True,
        }
        if image_url:
            payload["image_url"] = image_url
        return payload

    # DoP / Veo / Wan / cinematic (motion-only APIs — audio added via Runway TTS after)
    payload = {
        "prompt": prompt,
        "aspect_ratio": ratio,
        "duration": api_duration,
    }
    if image_url and spec.requires_image:
        payload["image_url"] = image_url
    return payload
