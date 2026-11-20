"""Read a designer-style creative brief deterministically, without asking an AI to guess its structure.

A common client file is a list of creatives, each a mini designer brief:

    ## Creative 3 – "Your Garden, Smarter From The Roots"
    **Creative Type:** Educational / Product Demonstration Static
    **MAIN HEADLINE:** ...        **SUBHEADLINE:** ...
    **VISUAL DIRECTION:** ...     (a cross-section, a 3-panel layout, arrows, a split screen...)
    **BENEFIT CALLOUTS:** ...     **BOTTOM CTA:** ...

The AI parser read such a file badly: it took "PANEL 1/2/3" and the arrows of a flow diagram
("WATER RESERVOIR ↓ WICKING SYSTEM ↓ PLANT ROOTS") for carousel cards, so six creatives became twelve
variants, headlines were lost, the visual direction was replaced by the headline text, and one creative's
CTA was copied onto the others.

Here one "Creative N" section is ONE image. Panels, arrows and callouts belong to that image. Every field
is taken exactly as written, and the whole brief becomes the variant's prompt (a complete designer brief, so
it is sent to the image model as written, with the brand style and art direction added after it).

It declines (returns []) for files that are not in this shape, so documents with real "Card 1 / Card 2"
carousels, tables, organic posts and the like keep going through the existing parsers.
"""

from __future__ import annotations

import re
from typing import Any

# "## Creative 3 – “Title”", "CREATIVE 7 – TITLE", "Creative 1: Title" (the heading marks are optional)
_SECTION = re.compile(r"^\s*(?:#{1,4}\s*)?[*_]*\s*creative\s*(\d+)\s*[–—:\-]+\s*(.*?)\s*[*_]*\s*$", re.IGNORECASE)
_CARD = re.compile(r"\b(?:card|slide)\s*\d+\b", re.IGNORECASE)
_RULE = re.compile(r"^[-*_=]{3,}$")

# What each label is called in the wild. Longer names are tried first so "bottom headline" is never read as
# "headline". Nothing here is specific to a client or an industry.
_ALIASES: dict[str, tuple[str, ...]] = {
    "type": ("creative type",),
    "headline": ("main headline", "headline"),
    "subheadline": ("subheadline", "sub headline", "sub-headline"),
    "pain": ("pain point",),
    "supporting": ("supporting text",),
    "visual": (
        "visual direction",
        "designer instructions",
        "additional visual direction for the designer",
        "additional visual direction",
    ),
    "callouts": ("benefit callouts", "benefit callout", "bottom benefits", "callouts"),
    "message": (
        "centre/bottom message",
        "center/bottom message",
        "centre message",
        "center message",
        "bottom message",
        "bottom headline",
        "small supporting text",
        "offer",
    ),
    "cta": ("bottom cta", "cta"),
}
_KEY_BY_ALIAS = {alias: key for key, aliases in _ALIASES.items() for alias in aliases}
_LABEL = re.compile(
    r"^\s*[*_#>\-\s]*(" + "|".join(re.escape(a) for a in sorted(_KEY_BY_ALIAS, key=len, reverse=True)) + r")\s*[*_]*\s*:\s*[*_]*\s*(.*)$",
    re.IGNORECASE,
)
_SINGLE_LINE = {"type", "headline", "subheadline", "cta"}  # a note after these belongs to nobody
_FLOW_WORDS = ("↓", "↑", "→")


def _plain(text: str) -> str:
    return text.replace("**", "").replace("__", "").replace(" ", " ").strip()


def _sections(markdown: str) -> list[tuple[int, str, list[str]]]:
    found: list[tuple[int, str, list[str]]] = []
    for line in (markdown or "").splitlines():
        match = _SECTION.match(line)
        if match:
            title = _plain(match.group(2)).strip("“”\"' ")
            found.append((int(match.group(1)), title, []))
        elif found:
            found[-1][2].append(line)
    return found


def _fields(lines: list[str]) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    current = ""
    for raw in lines:
        line = raw.strip()
        if not line or _RULE.match(line):
            continue  # a blank line does not end a field: lists have gaps
        label = _LABEL.match(line)
        if label:
            current = _KEY_BY_ALIAS[label.group(1).lower()]
            fields.setdefault(current, [])
            rest = _plain(label.group(2))
            if rest:
                fields[current].append(rest)
            continue
        if current:
            fields[current].append(_plain(line))
    return fields


def _first(fields: dict[str, list[str]], key: str) -> str:
    values = fields.get(key) or []
    return values[0].strip().strip("“”\"") if values else ""


def _tick(lines: list[str]) -> list[str]:
    ticked = []
    for line in lines:
        text = line.lstrip("✓✔☑•*- ").strip()
        if text:
            ticked.append(f"✓ {text}")
    return ticked


def _visual(lines: list[str]) -> tuple[str, bool]:
    """The visual direction as written, with a flow of arrows written on one line. True if it has a flow."""
    has_flow = any(any(w in line for w in _FLOW_WORDS) for line in lines)
    out: list[str] = []
    for line in lines:
        if line in _FLOW_WORDS:
            if out:
                out[-1] = out[-1].rstrip() + " →"
            continue
        if out and out[-1].endswith(" →"):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    text = "\n".join(out)
    for word in _FLOW_WORDS:
        text = text.replace(word, "→")
    return re.sub(r"\s*→\s*", " → ", text), has_flow


def _angle(creative_type: str) -> str:
    t = creative_type.lower()
    rules = (
        (("educational", "demonstration", "how-to", "how to"), "educational"),
        (("problem", "direct response"), "problem_agitate_solve"),
        (("testimonial", "review"), "testimonial"),
        (("social proof",), "social_proof"),
        (("offer", "urgency", "sale"), "offer_urgency"),
        (("product range", "catalogue", "catalog", "product hero"), "product_hero"),
    )
    for words, angle in rules:
        if any(w in t for w in words):
            return angle
    return ""


def _prompt(number: int, title: str, fields: dict[str, list[str]]) -> str:
    visual, has_flow = _visual(fields.get("visual", []))
    title = title.rstrip(" .:;")  # a title that already ends in a full stop must not get a second one
    end = "" if title.endswith(("?", "!")) else "."  # a question stays a question
    parts = [f"Creative {number}: {title}{end}" if title else f"Creative {number}."]
    if _first(fields, "type"):
        parts.append(f"Creative type: {_first(fields, 'type')}.")
    parts.append(f'Main headline: "{_first(fields, "headline")}"')
    if _first(fields, "subheadline"):
        parts.append(f"Subheadline: {_first(fields, 'subheadline')}")
    if fields.get("pain"):
        parts.append("Pain point: " + " ".join(fields["pain"]))
    if fields.get("supporting"):
        parts.append("Supporting text: " + " ".join(fields["supporting"]))
    if visual:
        parts.append("Visual direction:\n" + visual)
    if fields.get("callouts"):
        parts.append("Benefit callouts: " + " ".join(_tick(fields["callouts"])))
    if fields.get("message"):
        parts.append("Message: " + " ".join(fields["message"]))
    if _first(fields, "cta"):
        parts.append(f'CTA button: "{_first(fields, "cta")}"')
    if has_flow:
        parts.append("The arrows are a flow diagram drawn inside this one image, not separate slides or cards.")
    return "\n".join(parts)


def parse_designer_creatives(markdown: str, fallback_cta: str = "") -> list[dict[str, Any]]:
    """One variant per 'Creative N' section, or [] when the file is not in this shape."""
    sections = _sections(markdown)
    if not sections:
        return []
    if any(_CARD.search(" ".join(lines)) for _, _, lines in sections):
        return []  # real carousel cards: the carousel parser handles those
    variants: list[dict[str, Any]] = []
    for number, title, lines in sections:
        fields = _fields(lines)
        if not _first(fields, "headline"):
            continue  # a section with no main headline is not a brief
        creative_type = _first(fields, "type")
        visual_text = " ".join(fields.get("visual", [])).lower()
        graphic = any(w in f"{creative_type} {visual_text}".lower() for w in ("illustration", "diagram", "cross-section", "collage", "infographic", "split-screen", "split screen"))
        variants.append(
            {
                "id": f"C{number}",
                "format": "static",  # one section = one image; panels and arrows belong to it
                "ad_angle": _angle(creative_type),
                "hook": _first(fields, "headline"),
                "message": _first(fields, "subheadline"),
                "image_hook": _first(fields, "headline")[:80],
                "image_headline": _first(fields, "subheadline")[:100],
                "cta": _first(fields, "cta") or fallback_cta,
                "prompt": _prompt(number, title, fields),
                "creative_type": "graphic" if graphic else "photo",
                "post_type": creative_type,
                "reasoning": title,
                "prompt_complete": True,
            }
        )
    return variants
