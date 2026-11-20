"""Tell the image model how punchy the ad has to be, not just what words to print.

A plain "headline + three lines + button" prompt gives a plain ad. A designer's brief is more than that:
the hook is the biggest thing on the page, its payoff words are highlighted, the proof is a tick list, the
offer sits in a banner, the button is loud, and the hook follows a known angle (pain, proof, curiosity...).
This module writes that art direction into the prompt, once, on every static/carousel ad whose text the
model draws (when the app draws the text itself, ad_image_text.py adds the highlight).

It never replaces the user's own words: "where the brief above states a layout, follow it exactly".
It also stops people appearing where nobody asked for one.
"""

from __future__ import annotations

import hashlib
import random
import re

MARKER = "ART DIRECTION"

# One line per hook angle: how the creative should feel. Keys are the app's ad-angle ids.
ANGLE_PUNCH = {
    "problem_agitate_solve": "Show the problem, sharpen the pain, then land the fix in the offer: tension up top, relief at the bottom.",
    "pain_led": "Open on the pain in the viewer's own words and make its cost visible and specific.",
    "pattern_interrupt": "Break the scroll with one unexpected, high-contrast element and a blunt headline.",
    "social_proof": "Lead with the proof (the number, the rating, the result) as large as the headline.",
    "testimonial": "The quote is the hero: large, attributed, with the rating.",
    "before_after": "Make the contrast the picture: a clear before next to an after, framed the same way.",
    "offer_urgency": "The offer and its deadline dominate: a bold banner and a button that says go.",
    "educational": "Teach one thing clearly: a simple labelled visual and a headline that promises the lesson.",
    "myth_busting": "State the myth, strike it, give the truth: the contrast is the hook.",
    "curiosity_hook": "Open a loop: tease the answer and show just enough that the viewer needs the click.",
    "fear_loss_aversion": "Make the loss concrete (money, leads, time) and show it leaking away.",
    "fomo_scarcity": "Show the limit honestly (spots, dates) and what is missed by waiting.",
    "contrarian": "Take a clear, unpopular stance in the headline and own it.",
    "ugc_style": "Feel like a real post, not an ad: casual, native and a little imperfect.",
    "founder_led": "A direct, personal message: authentic over polished.",
    "product_hero": "The product is the hero, huge in frame, with a bold headline in the brand colours.",
}

# How the HEADLINE is set, one treatment per creative so a batch does not repeat the same look. These
# are about type and emphasis only (never the picture's subject), so they fit any industry and never
# fight a layout the brief states. {phrase} = the payoff words, {colour} = the accent.
TREATMENTS: list[str] = [
    'a marker-style block{colour} behind the payoff words "{phrase}" with a hand-drawn underline stroke, rest of the headline solid white or dark',
    'the headline stacked on two or three tight left-aligned lines, with the payoff words "{phrase}" set much larger{colour}, no boxes',
    'the headline on a solid full-width ribbon across the top{colour}, the payoff words "{phrase}" in a contrasting colour inside the ribbon',
    'the payoff words "{phrase}" circled by a loose hand-drawn ellipse{colour} with a small arrow pointing at the picture, the rest in clean heavy type',
    'the headline split in two tones: the first half in white or dark, the payoff words "{phrase}" in the accent colour, set on a darkened panel for contrast',
    'the payoff words "{phrase}" on a slightly rotated sticker or badge shape{colour}, the rest of the headline in bold condensed uppercase',
    'heavy condensed uppercase type with a crisp offset shadow and a thin keyline{colour} around the payoff words "{phrase}"',
    'the headline on a rounded solid card with an accent bar along its top edge{colour}, the payoff words "{phrase}" in the accent colour',
]


def treatment_for(index: int | None, seed: str, hook: str = "") -> str:
    """The Nth creative of a brief gets the Nth treatment of a shuffle seeded by the brief (a batch is all
    different until the list is used up). With no index (one image regenerated alone) it is a stable pick
    from the hook text."""
    pool = list(TREATMENTS)
    random.Random(f"punch:{seed}").shuffle(pool)
    if index is None:
        digest = int(hashlib.sha256(f"{seed}|{hook}".encode("utf-8")).hexdigest(), 16)
        return pool[digest % len(pool)]
    return pool[max(0, int(index)) % len(pool)]


_MARKED = re.compile(r"\*\*(.+?)\*\*")
_QUOTED = re.compile(r"[\"“”'‘’][^\"“”'‘’]{3,}[\"“”'‘’]")
_HEADLINE = re.compile(r"(?i)\b(?:main\s+)?headline\s*[:\-]\s*[\"“]([^\"”]{5,200})[\"”]")
# Words that mean a human is in the picture. "people" and "customers" are not here: they appear in headlines.
_PERSON = re.compile(
    r"(?i)\b(?:man|men|woman|women|person|portrait|face|faces|model|owner|founder|manager|couple|team|"
    r"hand|hands|smiling|smile|worker|doctor|dentist|customer photo|selfie)\b"
)


def parse_marked(text: str) -> tuple[str, set[int]]:
    """'Your budget leaking **every click**?' -> ('Your budget leaking every click?', {3, 4}).

    The user can mark the words to highlight with **double asterisks**; the asterisks are never printed.
    """
    tokens = (text or "").split()
    clean: list[str] = []
    marked: set[int] = set()
    inside = False
    for token in tokens:
        word = token.replace("**", "")
        if token.startswith("**"):
            inside = True
        if inside and word:
            marked.add(len(clean))
        if word:
            clean.append(word)
        rest = token[2:] if token.startswith("**") else token
        if "**" in rest:  # a closing marker, possibly followed by punctuation ("click**?")
            inside = False
    return " ".join(clean), marked


def payoff_indices(text: str) -> set[int]:
    """Which words of a hook to highlight: the ones marked with ** if any, else its payoff, the last one
    or two words ("... will NEVER BUY?")."""
    clean, marked = parse_marked(text)
    if marked:
        return marked
    words = clean.split()
    if len(words) < 3:
        return set()
    count = 2 if len(words) >= 4 else 1
    if len(re.sub(r"\W", "", words[-1])) <= 2 and count < len(words):  # a dangling "to"/"AI": take one more
        count += 1
    return set(range(len(words) - count, len(words)))


def highlight_phrase(text: str) -> str:
    clean, _ = parse_marked(text)
    words = clean.split()
    return " ".join(words[i] for i in sorted(payoff_indices(text)))


def extract_main_headline(prompt: str) -> str:
    """The quoted 'Main headline: "..."' of a pasted designer brief, or ''."""
    match = _HEADLINE.search(prompt or "")
    return " ".join(match.group(1).split()) if match else ""


def mentions_person(prompt: str) -> bool:
    """True if the prompt itself asks for a human (quoted headline text is ignored)."""
    return bool(_PERSON.search(_QUOTED.sub(" ", prompt or "")))


def punch_block(
    *, hook: str = "", accent: str = "", angle: str = "", allow_people: bool = True, treatment: str = ""
) -> str:
    phrase = highlight_phrase(hook)
    parts = [
        f"{MARKER} (where the brief above states a layout, follow it exactly; otherwise do this): make it scroll-stopping and punchy. "
        "One idea, one hook. The picture must show what the headline claims, so the viewer gets the message from the image "
        "alone; keep every label and callout short and large enough to read."
    ]
    angle_line = ANGLE_PUNCH.get((angle or "").strip().lower())
    if angle_line:
        parts.append(angle_line)
    colour = f" in {accent}" if accent else " in the brand accent colour"
    if phrase:
        look = (treatment or TREATMENTS[0]).format(phrase=phrase, colour=colour)
        parts.append(
            "The headline is the largest element, in heavy high-contrast type that reads in one second. Headline treatment for "
            f"this creative: {look}. Do not reuse a generic highlight style; this look is specific to this image."
        )
    else:
        parts.append("The headline is the largest element, in heavy high-contrast type that reads in one second.")
    parts.append(
        "Supporting points are short lines, as a tick list when there are two to four. The offer goes in a full-width banner "
        "and the call to action is a large, high-contrast button with an arrow. Use the brand colours for every emphasis."
    )
    if not allow_people:
        parts.append("Do not add people, faces or hands: the brief does not ask for them.")
    return " ".join(parts)


def apply_punch(
    prompt: str,
    *,
    hook: str = "",
    accent: str = "",
    angle: str = "",
    index: int | None = None,
    seed: str = "",
) -> str:
    """The prompt with the art direction added once, after the user's words and before the brand style."""
    text = (prompt or "").rstrip()
    if not text or MARKER in text:
        return text
    block = punch_block(
        hook=hook,
        accent=accent,
        angle=angle,
        allow_people=mentions_person(text),
        treatment=treatment_for(index, seed, hook),
    )
    return f"{text} {block}"
