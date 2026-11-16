"""Find the image spots in a customer's own email HTML and swap only their sources.

The customer's HTML is never re-serialised. We locate each picture with the standard
library parser, remember the exact character range of its address, and on export
replace just those characters. Everything else — text, tables, conditional comments
for Outlook, merge tags such as ``{{first_name}}``, links and the unsubscribe block —
stays byte-for-byte identical.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

MAX_HTML_CHARS = 400_000

_TRACKING_HINTS = (
    "track", "pixel", "beacon", "open.gif", "/o.gif", "spacer", "blank.gif", "clear.gif",
    "1x1", "analytics", "/open?", "/wf/open",
)
_ICON_HINTS = (
    "facebook", "twitter", "instagram", "linkedin", "youtube", "tiktok", "pinterest",
    "whatsapp", "social", "icon", "arrow", "bullet", "badge", "app-store", "google-play",
    "appstore", "googleplay",
)
_LOGO_HINTS = ("logo", "brand", "wordmark")

# Planned picture shapes when the template does not say how big a spot is.
# Hero / content pictures default to 3:2 landscape (the generators' native shape),
# products to a square.
_DEFAULT_WIDTH = {"hero": 600, "content": 600, "product": 300, "banner": 600, "other": 400}


@dataclass
class _RawSlot:
    index: int
    kind: str  # "img" | "background"
    raw_value: str  # exactly as written in the HTML (may contain &amp;)
    value_start: int  # absolute character offsets of the address inside the HTML
    value_end: int
    alt: str
    width: int | None
    height: int | None
    context_text: str
    tag: str


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for match in re.finditer("\n", text):
        starts.append(match.end())
    return starts


_ATTR_RE = re.compile(
    r"""([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?""",
    re.S,
)


def _attribute_spans(raw_tag: str) -> dict[str, tuple[str, int, int]]:
    """Map attribute name -> (value, start, end) relative to the raw start tag text."""
    name_end = re.match(r"<\s*[^\s/>]+", raw_tag)
    pos = name_end.end() if name_end else 0
    spans: dict[str, tuple[str, int, int]] = {}
    for match in _ATTR_RE.finditer(raw_tag, pos):
        name = match.group(1).lower()
        if match.group(2) is not None:
            value, group = match.group(2), 2
        elif match.group(3) is not None:
            value, group = match.group(3), 3
        elif match.group(4) is not None:
            value, group = match.group(4), 4
        else:
            continue
        spans.setdefault(name, (value, match.start(group), match.end(group)))
    return spans


def _px(value: str | None) -> int | None:
    if value is None:
        return None
    text = html_lib.unescape(value).strip().lower()
    match = re.fullmatch(r"([\d.]+)\s*(?:px)?", text)
    if not match:
        return None  # percentages, auto, em ... are not a fixed size
    try:
        number = int(round(float(match.group(1))))
    except ValueError:
        return None
    return number if number > 0 else None


def _style_px(style: str, prop: str) -> int | None:
    match = re.search(rf"(?<![-\w]){prop}\s*:\s*([\d.]+)px", style, re.I)
    return _px(match.group(1)) if match else None


_STYLE_URL_RE = re.compile(r"""url\(\s*(['"]?)(.*?)\1\s*\)""", re.I | re.S)


class _SlotParser(HTMLParser):
    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        self._text = text
        self._starts = _line_starts(text)
        self.slots: list[_RawSlot] = []
        self._last_text = ""
        self._in_style_or_script = False

    # ── text context ────────────────────────────────────────────────────────
    def handle_data(self, data: str) -> None:
        if self._in_style_or_script:
            return
        cleaned = re.sub(r"\s+", " ", html_lib.unescape(data)).strip()
        if len(cleaned) >= 3:
            self._last_text = cleaned[:160]

    # ── tags ────────────────────────────────────────────────────────────────
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script"):
            self._in_style_or_script = True
        raw = self.get_starttag_text() or ""
        line, col = self.getpos()
        start = self._starts[line - 1] + col
        if not raw or self._text[start : start + len(raw)] != raw:
            return  # positions disagree; never guess
        spans = _attribute_spans(raw)
        style_value = spans.get("style", ("", 0, 0))[0]
        style = html_lib.unescape(style_value)
        width = _px(spans.get("width", (None,))[0]) or _style_px(style, "width") or _style_px(style, "max-width")
        height = _px(spans.get("height", (None,))[0]) or _style_px(style, "height")
        alt = html_lib.unescape(spans.get("alt", ("",))[0]).strip()

        if tag == "img" and "src" in spans:
            value, v_start, v_end = spans["src"]
            if value.strip():
                self._add("img", value, start + v_start, start + v_end, alt, width, height, tag)
        elif "background" in spans and tag in {"table", "td", "th", "tr", "body", "div", "v:fill"}:
            value, v_start, v_end = spans["background"]
            if value.strip():
                self._add("background", value, start + v_start, start + v_end, alt, width, height, tag)
        if "style" in spans and "background" in style.lower():
            value, s_start, _ = spans["style"]
            url_match = _STYLE_URL_RE.search(value)
            if url_match and url_match.group(2).strip():
                self._add(
                    "background",
                    url_match.group(2),
                    start + s_start + url_match.start(2),
                    start + s_start + url_match.end(2),
                    alt,
                    width,
                    height,
                    tag,
                )

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self._in_style_or_script = False

    def _add(
        self, kind: str, raw_value: str, v_start: int, v_end: int, alt: str,
        width: int | None, height: int | None, tag: str,
    ) -> None:
        self.slots.append(
            _RawSlot(
                index=len(self.slots) + 1,
                kind=kind,
                raw_value=raw_value,
                value_start=v_start,
                value_end=v_end,
                alt=alt,
                width=width,
                height=height,
                context_text=self._last_text,
                tag=tag,
            )
        )


def _guess_role(src: str, alt: str, width: int | None, height: int | None, kind: str, is_first_large: bool) -> tuple[str, str | None]:
    """Return (role, reason_not_replaceable)."""
    low = f"{src} {alt}".lower()
    if (width is not None and width <= 3) or (height is not None and height <= 3):
        return "tracking", "Looks like a tracking pixel or spacer"
    if any(hint in src.lower() for hint in _TRACKING_HINTS) and (width is None or width <= 60):
        return "tracking", "Looks like a tracking pixel or spacer"
    if any(hint in low for hint in _ICON_HINTS) and (width is None or width <= 120):
        return "icon", "Looks like an icon or social button"
    if width is not None and width <= 64 and (height is None or height <= 64):
        return "icon", "Too small to be a picture (icon)"
    if any(hint in low for hint in _LOGO_HINTS) and (width is None or width <= 320):
        return "logo", "Looks like your logo — keep your official logo"
    if kind == "background" and (width is None or width >= 400):
        return "banner", None
    if is_first_large or (width is not None and width >= 480):
        return "hero", None
    if width is not None and height is not None and 0.8 <= width / height <= 1.25:
        return "product", None
    return "content", None


def _plan_size(role: str, width: int | None, height: int | None) -> tuple[int, int]:
    if width and height:
        return width, height
    base_w = width or _DEFAULT_WIDTH.get(role, 400)
    if height:
        return base_w, height
    if role == "product":
        return base_w, base_w
    return base_w, round(base_w * 2 / 3)  # 3:2 landscape


def analyze_email_html(html: str) -> dict[str, Any]:
    """List the image spots in an email. Never modifies the HTML."""
    text = html or ""
    if len(text) > MAX_HTML_CHARS:
        raise ValueError(f"Email HTML is too large (limit {MAX_HTML_CHARS:,} characters)")
    parser = _SlotParser(text)
    parser.feed(text)
    parser.close()

    slots: list[dict[str, Any]] = []
    seen_large = False
    for raw in parser.slots:
        src = html_lib.unescape(raw.raw_value).strip()
        is_first_large = not seen_large and (raw.width or 0) >= 400
        role, reason = _guess_role(src, raw.alt, raw.width, raw.height, raw.kind, is_first_large)
        if role in {"hero", "banner"}:
            seen_large = True
        plan_w, plan_h = _plan_size(role, raw.width, raw.height)
        slots.append(
            {
                "id": f"s{raw.index}",
                "kind": raw.kind,
                "src": src,
                "alt": raw.alt,
                "display_width": raw.width,
                "display_height": raw.height,
                "plan_width": plan_w,
                "plan_height": plan_h,
                "size_assumed": not (raw.width and raw.height),
                "aspect": round(plan_w / plan_h, 3),
                "role": role,
                "replaceable": reason is None,
                "reason": reason,
                "context_text": raw.context_text,
                "is_inline_data": src.lower().startswith("data:"),
            }
        )
    return {
        "slots": slots,
        "slot_count": len(slots),
        "replaceable_count": sum(1 for s in slots if s["replaceable"]),
        "merge_tags": sorted(set(re.findall(r"\{\{[^}]{1,60}\}\}|\*\|[A-Z0-9_:]{1,40}\|\*|%%[^%]{1,40}%%", text)))[:30],
        "html_length": len(text),
    }


_HTTP_RE = re.compile(r"^https?://[^\s\"'<>]+$", re.I)


def apply_image_replacements(html: str, replacements: dict[str, str]) -> dict[str, Any]:
    """Swap the address of the chosen slots and nothing else.

    ``replacements`` maps a slot id ("s3") to an absolute http(s) image URL.
    """
    text = html or ""
    if len(text) > MAX_HTML_CHARS:
        raise ValueError(f"Email HTML is too large (limit {MAX_HTML_CHARS:,} characters)")
    parser = _SlotParser(text)
    parser.feed(text)
    parser.close()
    by_id = {f"s{slot.index}": slot for slot in parser.slots}

    applied: list[str] = []
    skipped: list[dict[str, str]] = []
    edits: list[tuple[int, int, str]] = []
    chosen: dict[str, str] = {}
    for slot_id, new_url in replacements.items():
        slot = by_id.get(slot_id)
        if slot is None:
            skipped.append({"id": slot_id, "reason": "No such image spot in this HTML"})
            continue
        url = (new_url or "").strip()
        if not _HTTP_RE.match(url):
            skipped.append({"id": slot_id, "reason": "Replacement must be an absolute http(s) URL"})
            continue
        escaped = html_lib.escape(url, quote=True)
        edits.append((slot.value_start, slot.value_end, escaped))
        chosen[slot_id] = escaped
        applied.append(slot_id)

    out = text
    for start, end, value in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:start] + value + out[end:]

    # The same picture is often repeated for Outlook (VML) or in a <style> block. When
    # every spot that uses an old address was replaced with one new address, update those
    # remaining src= / background= / url() occurrences too, so no client shows the old image.
    groups: dict[str, list[str]] = {}
    for slot_id, slot in by_id.items():
        groups.setdefault(slot.raw_value, []).append(slot_id)
    for old_raw, ids in groups.items():
        new_values = {chosen.get(i) for i in ids}
        if None in new_values or len(new_values) != 1 or not old_raw.strip():
            continue
        new_value = next(iter(new_values))
        # The lookahead makes the old address end exactly here, so "a.jpg" never matches
        # the start of a different address such as "a.jpg?v=2".
        pattern = re.compile(
            r"((?:\bsrc|\bbackground)\s*=\s*[\"']?|url\(\s*[\"']?)"
            + re.escape(old_raw)
            + r"(?=[\"'\s)>/]|$)"
        )
        out = pattern.sub(lambda m: m.group(1) + new_value, out)

    warnings: list[str] = []
    if any(re.match(r"^https?://(localhost|127\.0\.0\.1)", html_lib.unescape(v), re.I) for v in chosen.values()):
        warnings.append(
            "Some images point at localhost, so they will not load for email recipients. "
            "Set PUBLIC_APP_URL to your public https address."
        )
    return {"html": out, "applied": applied, "skipped": skipped, "warnings": warnings}
