"""Detect media type from file bytes (extension may be wrong)."""

from __future__ import annotations

from pathlib import Path


def sniff_media_type(content: bytes, *, fallback_path: Path | None = None) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if len(content) >= 8 and content[4:8] == b"ftyp":
        return "video/mp4"
    if fallback_path is not None:
        guessed, _ = __import__("mimetypes").guess_type(str(fallback_path))
        if guessed:
            return guessed
    return "application/octet-stream"


def image_suffix_and_type(content: bytes, *, fallback_suffix: str = "") -> tuple[str, str]:
    media_type = sniff_media_type(content)
    suffix_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    suffix = suffix_map.get(media_type)
    if not suffix and fallback_suffix:
        fs = fallback_suffix.lower()
        if not fs.startswith("."):
            fs = f".{fs}"
        if fs in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            suffix = ".jpg" if fs == ".jpeg" else fs
            media_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
            }[suffix]
    if not suffix:
        raise ValueError(f"Unsupported image bytes (type={media_type})")
    return suffix, media_type


def video_suffix_and_type(content: bytes) -> tuple[str, str]:
    media_type = sniff_media_type(content)
    if media_type == "video/mp4":
        return ".mp4", media_type
    if content.startswith(b"\x89PNG") or content[:3] == b"\xff\xd8\xff":
        raise ValueError("Expected video bytes but received an image")
    return ".mp4", "video/mp4"
