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


def _size_for(api_model: str, format_type: str) -> str:
    ft = (format_type or "").lower()
    portrait = ft in {"reel", "stories"}
    landscape = ft in {"video", "carousel"}
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
        reference_purpose: str = "product",
    ) -> dict:
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

        size = _size_for(api_model, format_type)
        prompt_limit = 32_000 if api_model.startswith("gpt-image") else 4_000
        clamp_model = "gpt_image_2" if api_model.startswith("gpt-image") else None
        safe_prompt = clamp_runway_image_prompt(
            prompt or "",
            max_len=prompt_limit,
            model=clamp_model,
        )

        # Product / style reference → GPT Image edits endpoint (image + text)
        ref_url = (reference_image_url or "").strip() or None
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
                reference_image_url=ref_url,
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
        reference_image_url: str,
        original_prompt: str,
    ) -> dict:
        loaded = _load_reference_image_bytes(reference_image_url)
        if not loaded:
            return {
                "status": "failed",
                "model": api_model,
                "prompt": original_prompt,
                "url": None,
                "provider": "openai",
                "error": "Could not load product reference image for GPT Image edit",
            }
        content, filename, mime = loaded
        base = (settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}"}
        url = f"{base}/images/edits"

        # Multipart: image[] + prompt — gpt-image-* product reference path
        files = [
            ("image[]", (filename, content, mime)),
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
                if response.status_code >= 400:
                    # Retry without input_fidelity (older models / proxies)
                    form.pop("input_fidelity", None)
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
                return await self._save_response_image(
                    client,
                    response,
                    api_model=api_model,
                    prompt=original_prompt,
                    tenant_id=tenant_id,
                    format_type=format_type,
                    logo_url=logo_url,
                    logo_on_light_url=logo_on_light_url,
                    note="Generated from attached product photo (GPT Image edit).",
                )
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
