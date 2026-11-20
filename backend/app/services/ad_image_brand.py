"""Make every ad image prompt carry the brand's saved colours and fonts.

What went wrong: the Brand Kit (colours, heading and body fonts) reached the job correctly, but the lines
that put them into the prompt only ran for prompts the app built itself. A prompt that came from the AI,
from the strategy file, or that the user pasted was sent as it was, so its brand colours and fonts were
never mentioned and the image model picked its own (a burgundy button on a gold-and-black brand).

Two things make this work:
  * it is added to EVERY ad image prompt, whatever its source, and it says it overrides any other colour
    or font named earlier in the prompt (the AI's own scene may name a different palette);
  * an image model cannot load a font by name, so each font is also described by what it looks like
    ("an elegant high-contrast display serif"), which it can follow.
"""

from __future__ import annotations

import colorsys
import re

MARKER = "BRAND STYLE"

# Describing a font by look is what an image model can follow. Names are matched case-insensitively.
_FONT_LOOKS: dict[str, str] = {
    "cormorant garamond": "an elegant high-contrast display serif",
    "cormorant": "an elegant high-contrast display serif",
    "playfair display": "a high-contrast didone serif",
    "didot": "a high-contrast didone serif",
    "bodoni": "a high-contrast didone serif",
    "garamond": "a classic old-style serif",
    "eb garamond": "a classic old-style serif",
    "baskerville": "a refined transitional serif",
    "libre baskerville": "a refined transitional serif",
    "times new roman": "a classic newspaper serif",
    "georgia": "a sturdy screen serif",
    "merriweather": "a sturdy, readable serif",
    "lora": "a warm, calligraphic serif",
    "crimson text": "a classic book serif",
    "pt serif": "a sturdy, readable serif",
    "cinzel": "a roman-capitals serif",
    "abril fatface": "a heavy fat-face display serif",
    "open sans": "a clean humanist sans-serif",
    "arimo": "a neutral Arial-style sans-serif",
    "liberation sans": "a neutral Arial-style sans-serif",
    "noto sans": "a clean, even humanist sans-serif",
    "nunito sans": "a clean, friendly sans-serif",
    "rubik": "a slightly rounded modern sans-serif",
    "barlow": "a sturdy, slightly condensed sans-serif",
    "barlow condensed": "a tall condensed sans-serif",
    "roboto condensed": "a tall condensed sans-serif",
    "archivo": "a sturdy grotesque sans-serif",
    "manrope": "a clean modern geometric sans-serif",
    "plus jakarta sans": "a clean modern geometric sans-serif",
    "league spartan": "a bold geometric sans-serif",
    "anton": "a very bold tall condensed display sans-serif",
    "fjalla one": "a bold condensed display sans-serif",
    "ibm plex sans": "a technical, neutral sans-serif",
    "space grotesk": "a quirky geometric grotesque sans-serif",
    "dm serif display": "a high-contrast display serif",
    "libre franklin": "a classic American grotesque sans-serif",
    "lato": "a warm, friendly sans-serif",
    "roboto": "a neutral modern sans-serif",
    "inter": "a neutral modern sans-serif",
    "montserrat": "a wide geometric sans-serif",
    "poppins": "a round geometric sans-serif",
    "raleway": "an elegant thin geometric sans-serif",
    "nunito": "a soft rounded sans-serif",
    "quicksand": "a soft rounded sans-serif",
    "kanit": "a bold, modern, slightly squared sans-serif",
    "oswald": "a tall condensed sans-serif",
    "bebas neue": "a tall condensed all-caps display sans-serif",
    "dm sans": "a clean geometric sans-serif",
    "work sans": "a clean grotesque sans-serif",
    "source sans pro": "a clean humanist sans-serif",
    "josefin sans": "an elegant geometric sans-serif",
    "ubuntu": "a friendly humanist sans-serif",
    "helvetica": "a neutral neo-grotesque sans-serif",
    "arial": "a neutral neo-grotesque sans-serif",
    "futura": "a geometric sans-serif",
    "avenir": "a clean geometric sans-serif",
    "gotham": "a wide geometric sans-serif",
    "proxima nova": "a clean modern sans-serif",
    "dancing script": "a flowing casual script",
    "great vibes": "a flowing formal calligraphy script",
}


def describe_font(name: str) -> str:
    """'Cormorant Garamond' -> 'Cormorant Garamond (an elegant high-contrast display serif)'."""
    from app.services.brand_fonts import parse_font_spec

    clean = parse_font_spec(name)[0]  # "Oswald, 700" -> "Oswald": the weight is not part of the name
    if not clean:
        return ""
    key = clean.lower()
    look = _FONT_LOOKS.get(key)
    if not look:
        for known, text in _FONT_LOOKS.items():  # "Open Sans Condensed", "Montserrat Alternates"...
            if key.startswith(known):
                look = text
                break
    if not look:
        if "script" in key or "hand" in key:
            look = "a script typeface"
        elif "mono" in key or "code" in key:
            look = "a monospaced typeface"
        elif "serif" in key and "sans" not in key:
            look = "a serif typeface"
        elif "sans" in key:
            look = "a sans-serif typeface"
    return f"{clean} ({look})" if look else f"{clean} (match this typeface's style)"


_HEX = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def normalize_hex(value: str | None) -> str:
    match = _HEX.match((value or "").strip())
    if not match:
        return ""
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return f"#{digits.upper()}"


def describe_colour(hex_value: str) -> str:
    """A plain colour word for a hex ('#DBB45A' -> 'gold'), so the model has a name as well as a code."""
    value = normalize_hex(hex_value)
    if not value:
        return ""
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, lightness, s = colorsys.rgb_to_hls(r, g, b)
    hue = h * 360
    if lightness < 0.07 or (lightness < 0.12 and s < 0.3):
        return "black"  # a very dark but clearly coloured value (deep navy) keeps its colour name
    if lightness > 0.93:
        return "white"
    if s < 0.12:
        return "light grey" if lightness > 0.7 else ("dark grey" if lightness < 0.35 else "grey")
    if hue < 12 or hue >= 345:
        name = "red"  # (an orange-red like #FC602C sits at about 15 degrees and must read as orange)
    elif hue < 38:
        name = "brown" if lightness < 0.35 else "orange"
    elif hue < 52:
        name = "gold" if s >= 0.35 and 0.4 <= lightness <= 0.75 else "yellow"
    elif hue < 70:
        name = "yellow"
    elif hue < 165:
        name = "green"
    elif hue < 200:
        name = "teal"
    elif hue < 255:
        name = "blue"
    elif hue < 290:
        name = "purple"
    else:
        name = "pink" if lightness > 0.45 else "magenta"
    if name not in {"gold", "brown"}:
        if lightness < 0.32:
            name = f"deep {name}"
        elif lightness > 0.78:
            name = f"light {name}"
    return name


def accent_label(hex_value: str | None) -> str:
    """'#A4D36B' -> '#A4D36B (green)': the colour as a code and a plain word, or '' when there is none."""
    value = normalize_hex(hex_value)
    if not value:
        return ""
    word = describe_colour(value)
    return f"{value} ({word})" if word else value


PALETTE_ROLES = ("primary", "secondary", "tertiary")


def select_palette(
    snap: dict | None,
    slot: dict | None,
    primary: str = "",
    secondary: str = "",
) -> tuple[str, str, str, bool]:
    """The brand colours one image should use: (primary, secondary, tertiary, is_subset).

    ``slot["palette"]`` lists the roles the user ticked on that variant ("primary", "secondary", "tertiary") and
    ``slot["palette_colors"]`` holds colour codes typed on that variant (they override the brand's).
    Nothing ticked (or no list) means every colour the brand has. Colours the brand does not have are skipped."""
    snap = snap or {}
    have = {
        "primary": normalize_hex(str(snap.get("primary_color") or primary or "")),
        "secondary": normalize_hex(str(snap.get("secondary_color") or secondary or "")),
        "tertiary": normalize_hex(str(snap.get("tertiary_color") or "")),
    }
    # Colour codes typed on this variant replace the brand's colour for that slot (and can fill an empty third slot).
    custom = slot.get("palette_colors") if isinstance(slot, dict) else None
    if isinstance(custom, dict):
        for role in PALETTE_ROLES:
            typed = normalize_hex(str(custom.get(role) or ""))
            if typed:
                have[role] = typed
    asked = slot.get("palette") if isinstance(slot, dict) else None
    chosen = [r for r in PALETTE_ROLES if isinstance(asked, list) and r in asked and have[r]]
    subset = bool(chosen) and len(chosen) < len([r for r in PALETTE_ROLES if have[r]])
    if not chosen:
        chosen = [r for r in PALETTE_ROLES if have[r]]
    return (
        have["primary"] if "primary" in chosen else "",
        have["secondary"] if "secondary" in chosen else "",
        have["tertiary"] if "tertiary" in chosen else "",
        subset,
    )


def brand_style_line(
    primary: str = "",
    secondary: str = "",
    font_heading: str = "",
    font_body: str = "",
    *,
    photo_only: bool = False,
    tertiary: str = "",
    only_these: bool = False,
) -> str:
    """One compact paragraph stating the brand's colours and fonts. '' when there is nothing to state."""
    colours = []
    for label, raw in (("primary", primary), ("secondary", secondary), ("tertiary", tertiary)):
        value = normalize_hex(raw)
        if value:
            word = describe_colour(value)
            colours.append(f"{label} {value}" + (f" ({word})" if word else ""))
    if photo_only:
        return (
            f"{MARKER} (overrides any other palette named above): let the brand colours, {', '.join(colours)}, show in the scene "
            "(wardrobe, props, light)."
            if colours
            else ""
        )
    heading, body = describe_font(font_heading), describe_font(font_body)
    fonts = []
    if heading:
        fonts.append(f"headline in {heading}")
    if body:
        fonts.append(f"supporting text and button in {body}" if heading else f"text in {body}")
    if not colours and not fonts:
        return ""
    parts = [f"{MARKER} (overrides any other colour or font named above):"]
    if colours:
        if len(colours) >= 3:
            parts.append(
                f"{', '.join(colours)}: the primary for the main banner, headline highlight and button, the secondary "
                "for supporting panels and text, the tertiary for small accents (icons, ticks, dividers)."
            )
        else:
            parts.append(f"{', '.join(colours)}, used for the lettering, button and accents.")
        if only_these:
            parts.append(
                "Use only these brand colours for every coloured element (plus white, black and grey neutrals); "
                "do not bring in any other brand colour."
            )
    if fonts:
        joined = "; ".join(fonts)
        parts.append(f"{joined[0].upper()}{joined[1:]}. Letter it in these typeface styles.")  # keep font names' case
    return " ".join(parts)


def apply_brand_style(
    prompt: str,
    *,
    primary: str = "",
    secondary: str = "",
    font_heading: str = "",
    font_body: str = "",
    photo_only: bool = False,
    tertiary: str = "",
    only_these: bool = False,
) -> str:
    """The prompt with the brand style stated once, at the end where it weighs most. Safe to call twice."""
    text = (prompt or "").rstrip()
    if MARKER in text:
        return text
    line = brand_style_line(
        primary, secondary, font_heading, font_body, photo_only=photo_only, tertiary=tertiary, only_these=only_these
    )
    return f"{text} {line}" if line else text
