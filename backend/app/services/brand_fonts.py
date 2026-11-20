"""Fetch the font saved on the Brand page, as a real font file, so the app can draw text in it.

An image model cannot use a font by name; it only imitates the look. To get the real thing the app draws
the headline itself (ad_image_text.py), which needs the font file. The Brand Kit stores a family name
("Cormorant Garamond"), so this looks it up on Google Fonts, downloads the TrueType file once and keeps it
on disk for next time.

Google Fonts serves plain TrueType (which Pillow reads) when the request looks like an old browser, and
WOFF2 (which Pillow cannot read) otherwise, hence the old user agent.

A family that is not on Google Fonts (a licensed or custom font) returns None, and the caller falls back to
letting the image model draw the text. Failures are remembered for a few hours so a missing font does not
slow every image down.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_CSS_URL = "https://fonts.googleapis.com/css"
_OLD_BROWSER = "Mozilla/4.0"
_TTF_URL = re.compile(r"url\((https://[^)]+?\.ttf)\)")
_MISSING_TTL_SECONDS = 6 * 3600
HEADING_WEIGHTS = (700, 600, 500, 400)
BODY_WEIGHTS = (700, 600, 400)


def clean_family(name: str | None) -> str:
    """Only letters, digits, spaces and hyphens: the name goes into a URL, so nothing else is allowed."""
    text = re.sub(r"[^A-Za-z0-9 \-]", " ", str(name or ""))
    return re.sub(r"\s+", " ", text).strip()[:60]


_WEIGHT_WORDS = {
    "thin": 100, "extralight": 200, "ultralight": 200, "light": 300, "regular": 400, "normal": 400, "book": 400,
    "medium": 500, "semibold": 600, "demibold": 600, "bold": 700, "extrabold": 800, "ultrabold": 800, "black": 900,
}


def parse_font_spec(text: str | None) -> tuple[str, int | None]:
    """What a person types in the font box -> (family, wanted weight or None).

    The Brand page's own hint is "Inter, 700", so people write "Oswald, 700", "Arimo, Regular",
    "Open Sans Bold", "Inter 600" or "Oswald, sans-serif". Only the family goes to Google Fonts;
    the weight is a preference, and CSS fallbacks like sans-serif are ignored.
    """
    parts = [p.strip().strip("'\"") for p in str(text or "").split(",")]
    family = clean_family(parts[0]) if parts else ""
    weight: int | None = None
    tokens = family.split()
    if len(tokens) >= 2:  # "Inter 700", "Open Sans Bold"
        last = tokens[-1].lower().replace("-", "")
        if last.isdigit() and len(last) == 3 and 100 <= int(last) <= 900:
            weight, family = int(last), " ".join(tokens[:-1])
        elif last in _WEIGHT_WORDS:
            weight, family = _WEIGHT_WORDS[last], " ".join(tokens[:-1])
    for segment in parts[1:]:
        word = segment.lower().replace("-", "").replace(" ", "")
        if word.isdigit() and 100 <= int(word) <= 900:
            weight = int(word)
        elif word in _WEIGHT_WORDS:
            weight = _WEIGHT_WORDS[word]
    return family, weight


def _slug(family: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")


def cache_dir() -> Path:
    from app.core.config import settings

    path = Path(settings.UPLOAD_DIR) / "_private" / "brand_fonts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _readable(path: Path) -> bool:
    from PIL import ImageFont

    try:
        ImageFont.truetype(str(path), 24)
        return True
    except Exception:  # noqa: BLE001 - any failure means "not a usable font file"
        return False


def _download(client, family: str, weight: int, target: Path) -> bool:
    response = client.get(_CSS_URL, params={"family": f"{family}:{weight}"}, headers={"User-Agent": _OLD_BROWSER})
    if response.status_code != 200:
        return False
    match = _TTF_URL.search(response.text)
    if not match:
        return False
    font = client.get(match.group(1))
    if font.status_code != 200 or len(font.content) < 1000:
        return False
    handle, temp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".part")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(font.content)
        if not _readable(Path(temp_name)):
            return False
        os.replace(temp_name, target)  # atomic: another request never sees half a file
        return True
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def font_file(family: str | None, weights: tuple[int, ...] = HEADING_WEIGHTS, *, client=None) -> Path | None:
    """The cached or freshly downloaded font file for a family, trying the weights in order. None if
    the family cannot be found."""
    name, wanted = parse_font_spec(family)  # accepts "Oswald", "Oswald, 700", "Open Sans Bold"
    if not name:
        return None
    if wanted:  # the weight they asked for goes first, the usual ones after it
        weights = tuple(dict.fromkeys((wanted, *weights)))
    folder, slug = cache_dir(), _slug(name)

    import httpx

    http = client
    try:
        # Weight by weight, most wanted first: use the file if we have it, otherwise download it. A weight
        # Google definitely does not have is remembered, so it is not asked for again on every image.
        for weight in weights:
            target = folder / f"{slug}-{weight}.ttf"
            if target.is_file() and target.stat().st_size > 1000:
                return target
            nope = folder / f"{slug}-{weight}.nope"
            if nope.is_file() and time.time() - nope.stat().st_mtime < _MISSING_TTL_SECONDS:
                continue
            if http is None:
                http = httpx.Client(timeout=15.0, follow_redirects=True)
            try:
                if _download(http, name, weight, target):
                    return target
                nope.write_text(str(time.time()))
            except Exception:  # noqa: BLE001 - network trouble must never break image generation
                logger.warning("Brand font download failed: %s %s", name, weight, exc_info=True)  # not remembered
        logger.warning("Brand font %r is not available on Google Fonts; text will be drawn by the image model", name)
        return None
    finally:
        if http is not None and client is None:
            http.close()


def load_pair(heading: str | None, body: str | None, *, client=None) -> dict[str, Path] | None:
    """{'heading': path, 'body': path} for the brand's two fonts, or None when the heading font cannot be
    had. A missing body font reuses the heading font, so one saved font is enough."""
    heading_path = font_file(heading, HEADING_WEIGHTS, client=client)
    if not heading_path:
        return None
    body_path = font_file(body, BODY_WEIGHTS, client=client) if parse_font_spec(body)[0] else None
    return {"heading": heading_path, "body": body_path or heading_path}
