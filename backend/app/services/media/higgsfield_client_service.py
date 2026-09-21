"""Async wrapper around the official higgsfield-client SDK."""

from __future__ import annotations

import io
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import higgsfield_client
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Higgsfield upload API only accepts these content_type literals (rejects octet-stream).
_HF_ALLOWED_UPLOAD_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
        "audio/x-wav",
        "audio/wav",
        "video/mp4",
    }
)


def _ensure_credentials_env() -> None:
    key = (settings.HIGGSFIELD_API_KEY or "").strip()
    secret = (settings.HIGGSFIELD_API_SECRET or "").strip()
    if not key or not secret:
        raise RuntimeError(
            "Higgsfield API is not configured. Set HIGGSFIELD_API_KEY and HIGGSFIELD_API_SECRET in .env"
        )
    os.environ["HF_API_KEY"] = key
    os.environ["HF_API_SECRET"] = secret
    os.environ["HF_KEY"] = f"{key}:{secret}"


def guess_higgsfield_upload_content_type(file_path: str | os.PathLike[str]) -> str:
    """MIME type safe for Higgsfield's upload URL endpoint (never octet-stream)."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    by_ext = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".wav": "audio/wav",
        ".mp4": "video/mp4",
        ".m4v": "video/mp4",
        ".mov": "video/mp4",
    }
    if suffix in by_ext:
        return by_ext[suffix]

    guessed, _ = mimetypes.guess_type(str(path))
    if guessed in _HF_ALLOWED_UPLOAD_TYPES:
        return "image/jpeg" if guessed == "image/jpg" else guessed

    try:
        head = path.read_bytes()[:32]
    except OSError:
        head = b""
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF8"):
        return "image/gif"
    if head.startswith(b"RIFF") and b"WEBP" in head[:16]:
        return "image/webp"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "video/mp4"

    return "image/png"


def png_bytes_to_jpeg(png_bytes: bytes, *, quality: int = 92) -> bytes:
    """Convert PNG seed frames to JPEG — often more reliable for S3 presigned PUTs."""
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes))
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


def extract_media_url(result: dict[str, Any]) -> str | None:
    images = result.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict) and first.get("url"):
            return str(first["url"])
    video = result.get("video")
    if isinstance(video, dict) and video.get("url"):
        return str(video["url"])
    jobs = result.get("jobs")
    if isinstance(jobs, list):
        for job in jobs:
            if not isinstance(job, dict):
                continue
            results = job.get("results")
            if isinstance(results, dict):
                raw = results.get("raw")
                if isinstance(raw, dict) and raw.get("url"):
                    return str(raw["url"])
    return None


def _friendly_hf_error(msg: str) -> str:
    low = (msg or "").lower()
    if "not_enough_credits" in low:
        return (
            "Higgsfield account has insufficient credits. Top up at https://cloud.higgsfield.ai"
        )
    if "model_not_found" in low or "model not found" in low:
        return (
            "Higgsfield model_not_found — this model path is not available on your account. "
            "For 10s video use Kling v3.0 (works now). Seedance 1.5 is not on this API; "
            "Seedance 2.0 may need enabling in cloud.higgsfield.ai."
        )
    if "model_disabled" in low:
        return (
            "Higgsfield model_disabled — Seedance is on your plan but turned off. "
            "Enable it in https://cloud.higgsfield.ai (Models), or use Kling v3.0 for 5–10s."
        )
    if "content_type" in low and "octet-stream" in low:
        return (
            "Higgsfield rejected the seed-frame upload (invalid content type). "
            "Retry Generate."
        )
    if "literal_error" in low and "content_type" in low:
        return (
            "Higgsfield rejected an upload content type. Retry Generate. "
            "If it persists, re-check HIGGSFIELD_API_KEY / SECRET."
        )
    if (
        "readerror" in low
        or "read error" in low
        or "connecterror" in low
        or "connection reset" in low
        or "timed out" in low
        or "timeout" in low
        or not (msg or "").strip()
    ):
        return (
            "Higgsfield connection dropped while generating (network/timeout). "
            "Credits may still have been charged — check cloud.higgsfield.ai, then Retry Generate."
        )
    return f"Higgsfield generation failed: {msg}"


async def subscribe_platform(
    platform_path: str,
    arguments: dict[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    _ensure_credentials_env()
    path = platform_path.lstrip("/")
    logger.info("Higgsfield %s: path=%s", label, path)
    try:
        return await higgsfield_client.subscribe_async(path, arguments)
    except Exception as exc:
        msg = str(exc)
        if "Model not found" in msg:
            raise RuntimeError(
                f"Higgsfield model path not available on your account: {path}. "
                "Try another model or check https://docs.higgsfield.ai"
            ) from exc
        raise RuntimeError(_friendly_hf_error(msg)) from exc


def _presign_requires_content_type(upload_url: str) -> bool:
    qs = parse_qs(urlparse(upload_url).query)
    signed = (qs.get("X-Amz-SignedHeaders") or qs.get("x-amz-signedheaders") or [""])[0]
    return "content-type" in signed.lower()


async def _put_upload(
    *,
    data: bytes,
    content_type: str,
) -> str:
    """Request a Higgsfield presigned URL and PUT bytes (fresh URL per attempt)."""
    client = higgsfield_client.async_client
    public_url, upload_url = await client._get_upload_url(content_type)
    must_send_ct = _presign_requires_content_type(upload_url)

    # Prefer exact Content-Type when the signature requires it (typical).
    attempts: list[dict[str, str] | None] = []
    if must_send_ct:
        attempts.append({"Content-Type": content_type})
    else:
        attempts.append({"Content-Type": content_type})
        attempts.append(None)

    last_status = 0
    last_body = ""
    for headers in attempts:
        # Fresh URL if retrying without Content-Type (signature must match headers used)
        if headers is None:
            public_url, upload_url = await client._get_upload_url(content_type)
        async with httpx.AsyncClient(timeout=120.0) as http:
            response = await http.put(upload_url, content=data, headers=headers or {})
        last_status = response.status_code
        last_body = (response.text or "")[:300]
        if response.status_code < 400:
            return public_url
        logger.warning(
            "Higgsfield S3 PUT failed status=%s headers=%s body=%s",
            response.status_code,
            list((headers or {}).keys()),
            last_body[:160],
        )

    # SDK path as last resort (same as their upload())
    try:
        return await client.upload(data, content_type)
    except Exception as sdk_exc:
        raise RuntimeError(
            f"Could not upload to Higgsfield S3 (HTTP {last_status}). "
            f"{last_body[:120] or str(sdk_exc)[:120]}"
        ) from sdk_exc


async def upload_bytes(
    data: bytes,
    *,
    content_type: str = "image/jpeg",
) -> str:
    """Upload raw bytes with an allowed Higgsfield content_type."""
    _ensure_credentials_env()
    ct = content_type if content_type in _HF_ALLOWED_UPLOAD_TYPES else "image/jpeg"
    if ct == "image/jpg":
        ct = "image/jpeg"
    return await _put_upload(data=data, content_type=ct)


async def upload_local_image(file_path: str) -> str:
    """Upload a local file to Higgsfield storage using an allowed image MIME type."""
    _ensure_credentials_env()
    path = Path(file_path)
    raw = path.read_bytes()
    content_type = guess_higgsfield_upload_content_type(path)

    # Prefer JPEG for stitch / seed re-uploads — fewer S3 signature issues than PNG.
    payloads: list[tuple[bytes, str]] = []
    if content_type == "image/png" or raw.startswith(b"\x89PNG"):
        try:
            payloads.append((png_bytes_to_jpeg(raw), "image/jpeg"))
        except Exception as conv_exc:
            logger.warning("PNG→JPEG convert failed: %s", conv_exc)
        payloads.append((raw, "image/png"))
    else:
        payloads.append((raw, content_type))
        if content_type == "image/jpeg":
            payloads.append((raw, "image/jpg"))

    last: Exception | None = None
    for data, ct in payloads:
        try:
            return await _put_upload(data=data, content_type=ct)
        except Exception as exc:
            last = exc
            logger.warning("Higgsfield upload as %s failed (%s)", ct, str(exc)[:160])
            continue

    raise RuntimeError(
        "Could not upload seed image to Higgsfield S3 (403). "
        "Your API key works for generation, but the file upload signature failed. "
        "Retry Generate; if it keeps failing, regenerate the key pair at cloud.higgsfield.ai."
    ) from last
