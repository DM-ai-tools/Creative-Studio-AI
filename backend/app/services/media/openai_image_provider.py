"""Generate images via the official OpenAI Images API (not Runway / Higgsfield)."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.file_service import file_service
from app.services.logo_overlay import apply_logo_overlay_to_file
from app.services.media.base import ImageGenerationProvider
from app.services.brand_prompt import clamp_runway_image_prompt
from app.services.media.openai_image_catalog import (
    openai_configured,
    resolve_openai_image_model,
)
from app.services.media_content import image_suffix_and_type

logger = logging.getLogger(__name__)


class ImagePersistenceError(RuntimeError):
    """The provider returned media, but the local asset could not be saved."""

# High quality on complex ad prompts often exceeds 180s and surfaces as an empty
# httpx.ReadTimeout message — prefer auto, then fall back to low on timeout.
_DEFAULT_GPT_IMAGE_QUALITY = "auto"
_REQUEST_TIMEOUT_SEC = 240.0


def _orientation_for_ratio(aspect_ratio: str | None) -> str | None:
    """'portrait' | 'landscape' | 'square' for "1:1", "4:5", "16:9", "1200x628"..., or None if unreadable."""
    raw = (aspect_ratio or "").strip().lower().replace("x", ":").replace("/", ":")
    parts = raw.split(":")
    if len(parts) != 2:
        return None
    try:
        width, height = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    ratio = width / height
    if ratio < 0.9:
        return "portrait"
    if ratio > 1.1:
        return "landscape"
    return "square"


def _size_for(api_model: str, format_type: str, aspect_ratio: str | None = None) -> str:
    ft = (format_type or "").lower()
    portrait = ft in {"reel", "stories"}
    landscape = ft in {"video", "carousel"}  # the format-name default (other callers rely on it)
    # When the caller states a ratio (the brief's ad images do), the ratio decides, so a 1:1 carousel
    # card is square like the static ad instead of landscape.
    chosen = _orientation_for_ratio(aspect_ratio)
    if chosen and ft in {"static", "carousel", ""}:
        portrait, landscape = chosen == "portrait", chosen == "landscape"
    if api_model.startswith("dall-e-2"):
        return "1024x1024"
    if api_model.startswith("dall-e-3"):
        if portrait:
            return "1024x1792"
        if landscape:
            return "1792x1024"
        return "1024x1024"
    # gpt-image-*
    if portrait:
        return "1024x1536"
    if landscape:
        return "1536x1024"
    return "1024x1024"


def _exc_message(exc: BaseException) -> str:
    """httpx timeouts often stringify to '' — always return something useful."""
    text = str(exc).strip()
    if text:
        return text[:800]
    name = type(exc).__name__
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return (
            f"{name}: OpenAI Images API timed out. "
            "Retry with GPT Image 1 Mini, or wait and regenerate - credits are fine."
        )
    return name or "OpenAI image generation failed"


def _load_reference_image_bytes(file_url: str) -> tuple[bytes, str, str] | None:
    """Return (bytes, filename, mime) for a local /files URL or remote http(s) image."""
    url = (file_url or "").strip()
    if not url:
        return None

    upload_root = Path(settings.UPLOAD_DIR).resolve()
    rel: Path | None = None
    if url.startswith("/files/"):
        rel = Path(url.removeprefix("/files/"))
    elif url.startswith("files/"):
        rel = Path(url.removeprefix("files/"))

    if rel is not None:
        path = (upload_root / rel).resolve()
        try:
            path.relative_to(upload_root)
        except ValueError:
            return None
        if not path.is_file():
            return None
        suffix = path.suffix.lower() or ".png"
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(suffix, "image/png")
        return path.read_bytes(), path.name or f"product{suffix}", mime

    if url.startswith("http://") or url.startswith("https://"):
        try:
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                content = resp.content
            suffix, mime = image_suffix_and_type(content)
            return content, f"product{suffix}", mime
        except Exception as exc:
            logger.warning("Could not download reference image %s: %s", url[:120], exc)
            return None

    if url.startswith("data:"):
        try:
            header, b64 = url.split(",", 1)
            mime = "image/png"
            if "image/" in header:
                mime = header.split(";")[0].split(":")[-1] or mime
            ext = ".png" if "png" in mime else ".jpg" if "jpeg" in mime or "jpg" in mime else ".webp"
            return base64.b64decode(b64), f"product{ext}", mime
        except Exception:
            return None
    return None


class OpenAIImageProvider(ImageGenerationProvider):
    provider_id = "openai"

    async def generate(
        self,
        *,
        prompt: str,
        tenant_id: str,
        model: str,
        format_type: str,
        logo_url: str | None = None,
        logo_on_light_url: str | None = None,
        reference_image_url: str | None = None,
        reference_image_urls: list[str] | None = None,
        reference_purpose: str = "product",
        target_video_model: str | None = None,
        aspect_ratio: str | None = None,
    ) -> dict:
        _ = target_video_model
        api_model = resolve_openai_image_model(model)
        if not openai_configured():
            return {
                "status": "failed",
                "model": api_model,
                "prompt": prompt,
                "url": None,
                "provider": "openai",
                "error": "OPENAI_API_KEY is not configured",
            }

        size = _size_for(api_model, format_type, aspect_ratio)
        prompt_limit = 32_000 if api_model.startswith("gpt-image") else 4_000
        clamp_model = "gpt_image_2" if api_model.startswith("gpt-image") else None
        safe_prompt = clamp_runway_image_prompt(
            prompt or "",
            max_len=prompt_limit,
            model=clamp_model,
        )

        # Product / style reference → GPT Image edits endpoint (image + text)
        ref_urls: list[str] = []
        for value in [reference_image_url, *(reference_image_urls or [])]:
            url = str(value or "").strip()
            if url and url not in ref_urls:
                ref_urls.append(url)
        ref_urls = ref_urls[:8]
        ref_url = ref_urls[0] if ref_urls else None
        purpose = (reference_purpose or "product").strip().lower()
        if ref_url and api_model.startswith("gpt-image"):
            if purpose in {"character", "cast", "person"}:
                fidelity = (
                    "CAST CONTINUITY: Match the attached reference person's face, hair, build, "
                    "skin tone, and wardrobe exactly across scenes. Do not swap to a different person."
                )
            elif purpose in {"style", "scene"}:
                fidelity = (
                    "STYLE CONTINUITY: Match the attached reference for lighting, palette, and "
                    "environment tone. Keep any people identical to the reference when present."
                )
            elif len(ref_urls) > 1:
                fidelity = (
                    f"PRODUCT FIDELITY: {len(ref_urls)} product photos are attached, in order "
                    f"(Image 1 to Image {len(ref_urls)}). Each is a different real product. Show every one of "
                    "them in the scene, each copied exactly from its own photo: same shape, colours, materials, "
                    "proportions, markings and branding. Do not merge two products into one, do not swap one "
                    "for another, and do not invent a product that is not in a photo."
                )
            else:
                fidelity = (
                    "PRODUCT FIDELITY: Match the attached product photo exactly — same shape, "
                    "colours, materials, proportions, and branding. Place that real product in the "
                    "new scene. Do not invent a different product."
                )
            safe_prompt = f"{safe_prompt}\n\n{fidelity}"[:prompt_limit]
            edited = await self._generate_with_reference(
                api_model=api_model,
                prompt=safe_prompt,
                size=size,
                tenant_id=tenant_id,
                format_type=format_type,
                logo_url=logo_url,
                logo_on_light_url=logo_on_light_url,
                reference_image_urls=ref_urls,
                reference_purpose=purpose,
                original_prompt=prompt,
            )
            if edited.get("status") in {"done", "mock"} or edited.get("url"):
                return edited
            if edited.get("retryable") is False:
                return edited
            logger.warning(
                "GPT Image reference edit failed (%s) — falling back to text-only generation",
                edited.get("error"),
            )

        payload: dict = {
            "model": api_model,
            "prompt": safe_prompt,
            "size": size,
        }
        if api_model.startswith("dall-e"):
            payload["n"] = 1
        if api_model.startswith("gpt-image"):
            payload["quality"] = _DEFAULT_GPT_IMAGE_QUALITY
        elif api_model.startswith("dall-e-3"):
            payload["quality"] = "hd"
            payload["response_format"] = "b64_json"

        base = (settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SEC) as client:
                response = await self._post_with_fallbacks(client, base, headers, payload)
                if response.status_code >= 400:
                    err_txt = (response.text or "")[:800]
                    logger.warning("OpenAI image failed (%s): %s", response.status_code, err_txt)
                    return {
                        "status": "failed",
                        "model": api_model,
                        "prompt": prompt,
                        "url": None,
                        "provider": "openai",
                        "error": (
                            f"OpenAI Images API {response.status_code}: {err_txt}"
                            if err_txt
                            else f"OpenAI Images API {response.status_code}"
                        ),
                    }
                return await self._save_response_image(
                    client,
                    response,
                    api_model=api_model,
                    prompt=prompt,
                    tenant_id=tenant_id,
                    format_type=format_type,
                    logo_url=logo_url,
                    logo_on_light_url=logo_on_light_url,
                    note=None,
                )
        except Exception as exc:
            logger.exception("OpenAI image generation failed")
            return {
                "status": "failed",
                "model": api_model,
                "prompt": prompt,
                "url": None,
                "provider": "openai",
                "error": _exc_message(exc),
            }

    async def _generate_with_reference(
        self,
        *,
        api_model: str,
        prompt: str,
        size: str,
        tenant_id: str,
        format_type: str,
        logo_url: str | None,
        logo_on_light_url: str | None,
        reference_image_urls: list[str],
        reference_purpose: str,
        original_prompt: str,
    ) -> dict:
        loaded_refs = [
            loaded
            for url in reference_image_urls[:8]
            if (loaded := _load_reference_image_bytes(url))
        ]
        if not loaded_refs:
            return {
                "status": "failed",
                "model": api_model,
                "prompt": original_prompt,
                "url": None,
                "provider": "openai",
                "error": "Could not load the reference image for GPT Image edit",
            }
        base = (settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}"}
        url = f"{base}/images/edits"

        # Multipart: image[] + prompt — gpt-image-* product reference path
        files = [
            ("image[]", (filename, content, mime))
            for content, filename, mime in loaded_refs
        ]
        form: dict[str, str] = {
            "model": api_model,
            "prompt": prompt,
            "size": size,
            "quality": _DEFAULT_GPT_IMAGE_QUALITY,
        }
        # High input fidelity keeps product shape/branding closer to the photo
        form["input_fidelity"] = "high"

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SEC) as client:
                response = await client.post(url, headers=headers, data=form, files=files)
                fidelity_dropped = False
                if response.status_code >= 400:
                    # Retry without input_fidelity (older models / proxies)
                    logger.warning(
                        "Image edit refused input_fidelity=high (%s): %s; retrying without it, the product may drift",
                        response.status_code,
                        (response.text or "")[:200],
                    )
                    form.pop("input_fidelity", None)
                    fidelity_dropped = True
                    response = await client.post(url, headers=headers, data=form, files=files)
                if response.status_code >= 400:
                    err_txt = (response.text or "")[:800]
                    return {
                        "status": "failed",
                        "model": api_model,
                        "prompt": original_prompt,
                        "url": None,
                        "provider": "openai",
                        "error": f"OpenAI Images edits {response.status_code}: {err_txt}",
                    }
                saved = await self._save_response_image(
                    client,
                    response,
                    api_model=api_model,
                    prompt=original_prompt,
                    tenant_id=tenant_id,
                    format_type=format_type,
                    logo_url=logo_url,
                    logo_on_light_url=logo_on_light_url,
                    note=(
                        "Generated from attached character references with high input fidelity."
                        if reference_purpose in {"character", "cast", "person"}
                        else "Generated from attached product photo (GPT Image edit)."
                    ),
                )
                # Say so on the image when the model did not get every photo or lost high fidelity.
                notes: list[str] = []
                if len(loaded_refs) < len(reference_image_urls[:8]):
                    logger.warning(
                        "Only %d of %d reference images could be loaded", len(loaded_refs), len(reference_image_urls[:8])
                    )
                    notes.append(
                        f"Only {len(loaded_refs)} of {len(reference_image_urls[:8])} product photos could be read, "
                        "so the others were not used. Re-upload them and regenerate."
                    )
                if fidelity_dropped:
                    notes.append("The image model did not accept high product fidelity, so the product may differ slightly.")
                if notes and isinstance(saved, dict):
                    saved["warnings"] = [*(saved.get("warnings") or []), *notes]
                return saved
        except ImagePersistenceError as exc:
            logger.exception("OpenAI image edit completed but could not be saved")
            return {
                "status": "failed",
                "model": api_model,
                "prompt": original_prompt,
                "url": None,
                "provider": "openai",
                "error": _exc_message(exc),
                "retryable": False,
            }
        except Exception as exc:
            logger.exception("OpenAI image edit (product reference) failed")
            return {
                "status": "failed",
                "model": api_model,
                "prompt": original_prompt,
                "url": None,
                "provider": "openai",
                "error": _exc_message(exc),
            }

    async def _save_response_image(
        self,
        client: httpx.AsyncClient,
        response: httpx.Response,
        *,
        api_model: str,
        prompt: str,
        tenant_id: str,
        format_type: str,
        logo_url: str | None,
        logo_on_light_url: str | None,
        note: str | None,
    ) -> dict:
        body = response.json()
        data = (body.get("data") or [None])[0] or {}
        content: bytes | None = None
        b64 = data.get("b64_json")
        if b64:
            content = base64.b64decode(b64)
        elif data.get("url"):
            dl = await client.get(str(data["url"]), timeout=120.0, follow_redirects=True)
            dl.raise_for_status()
            content = dl.content
        if not content:
            raise ValueError("OpenAI image response had no image bytes")

        suffix, content_type = image_suffix_and_type(content)
        try:
            saved = file_service.save_bytes(
                content=content,
                tenant_id=tenant_id,
                subfolder="generated",
                suffix=suffix,
                content_type=content_type,
            )
        except OSError as exc:
            raise ImagePersistenceError(
                "The image was generated, but Creative Studio could not save it locally. "
                "Check backend write access to the uploads directory."
            ) from exc
        final_url = saved["file_url"]
        logo_applied = False
        if logo_url and final_url:
            overlaid = apply_logo_overlay_to_file(
                final_url,
                logo_url,
                tenant_id=tenant_id,
                logo_on_light_url=logo_on_light_url,
                format_type=format_type,
            )
            if overlaid and overlaid != final_url:
                final_url = overlaid
                logo_applied = True
            elif overlaid:
                final_url = overlaid
        out = {
            "status": "done",
            "model": api_model,
            "prompt": prompt,
            "url": final_url,
            "provider": "openai",
            "logo_applied": logo_applied,
        }
        if note:
            out["note"] = note
        return out

    async def _post_with_fallbacks(
        self,
        client: httpx.AsyncClient,
        base: str,
        headers: dict,
        payload: dict,
    ) -> httpx.Response:
        """Try auto quality first; on HTTP error or timeout, retry low / square size."""
        url = f"{base}/images/generations"
        attempts: list[dict] = [dict(payload)]
        if payload.get("quality") in {"high", "auto"}:
            attempts.append({**payload, "quality": "low"})
        if payload.get("size") and payload.get("size") != "1024x1024":
            attempts.append({**payload, "quality": "low", "size": "1024x1024"})

        last_response: httpx.Response | None = None
        last_exc: BaseException | None = None
        seen: set[tuple] = set()
        for attempt in attempts:
            key = (attempt.get("quality"), attempt.get("size"))
            if key in seen:
                continue
            seen.add(key)
            try:
                response = await client.post(url, headers=headers, json=attempt)
            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "OpenAI image timeout model=%s quality=%s size=%s — retrying softer settings",
                    attempt.get("model"),
                    attempt.get("quality"),
                    attempt.get("size"),
                )
                continue
            last_response = response
            if response.status_code < 400:
                return response
            logger.warning(
                "OpenAI image HTTP %s model=%s quality=%s — trying fallback",
                response.status_code,
                attempt.get("model"),
                attempt.get("quality"),
            )

        if last_exc and last_response is None:
            raise last_exc
        assert last_response is not None
        return last_response
