"""Creative Studio "Script mode": turn a written production script into the timed prompt the
existing Creative Studio pipeline already understands.

The script (usually a Word document) says what happens, what is said, and how long each part
runs. An LLM reads it and, for every scene, writes the Seedance footage plus a to-do list of
what the editor lays over specific time windows (screens, text cards, logo end card...).

Nothing here generates video. The result is a *canonical prompt* in the same sectioned format
people already paste by hand (``SCENE 1 - TITLE | 0-8 SECONDS`` / ``Voiceover, 0-8 seconds:``).
The existing pipeline then does what it always does with such a prompt: chapters, character and
voice lock, continuity frames. Voice choices written in the script ("Australian English female
voice") are carried into that prompt so the existing voice lock picks them up.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_SCRIPT_CHARS = 60000
MIN_SCENE_SECONDS = 4  # Seedance's minimum clip length
MAX_SCENES = 60
WORDS_PER_SECOND = 2.5  # typical narration pace
MAX_END_CARD_SECONDS = 5.0  # an end card normally holds 2-4s; longer is flagged
END_CARD_DEFAULT_SECONDS = 4  # how long a card is held over an on-camera speaker's last words
MIN_SHOT_SECONDS = 2  # a cut faster than this reads as a glitch
MAX_SHOTS = 12  # per scene
STILL_KINDS = frozenset({"screen", "graphic"})  # editor inserts that can be drawn as an AI still
MIN_STILL_SECONDS, MAX_STILL_SECONDS = 2.0, 6.0
MAX_STILL_PROMPT_CHARS = 1500
LONG_SHOT_SECONDS = 6  # a single shot longer than this feels slow and is flagged
SCRIPT_PLAN_DEFAULT_MODEL = "openai/gpt-4.1"  # planner default; reached through OpenRouter
SPEECH_NATIVE = "native_presenter"  # Seedance speaks (default)
SPEECH_EXTERNAL = "external_voiceover"  # OpenAI voice

_SYSTEM = """You are a senior video producer preparing a script for AI video generation with Seedance.

You receive a production script. It describes, scene by scene, what is seen, what is spoken, and
usually the on-screen text. Follow the script's OWN scenes and order.

HOW THE VIDEO IS MADE
Seedance generates ONE continuous video for the whole timeline and speaks the voiceover itself,
in one consistent voice. An editor then lays graphics over it. So for EVERY scene you write
footage Seedance can generate for the scene's full length, and separately list what the editor
adds on top.

For each scene give:
- "shots": the footage for the WHOLE scene as a SHOT LIST, like a director's cut. A new shot every
  2-4 seconds (a 9 second scene has 3-4 shots; never one long take). Each shot is
  {"seconds": 2-5, "description": 25-55 words}; the shots' seconds add up to the scene's length.
  Make it feel energetic and cinematic, not a slow single camera move:
    - change framing and angle between shots (wide, medium, close-up, macro detail, overhead,
      over-the-shoulder, low angle) and give every shot clear visible ACTION and movement;
    - show different things, not the same person and desk again: people, hands, objects,
      environments, other characters, reactions, cutaways that ILLUSTRATE the words being spoken
      (turn each phrase of the voiceover into a concrete picture). AT LEAST HALF of every scene's
      shots must be cutaways: something other than the scene's main person at their main prop
      (for example customers, products, parcels, a street, hands doing something, a telling
      object, a crowd, a close detail that dramatises the idea). Where the script's own direction
      is plain (a person at a laptop), keep it as the anchor and add cutaways around it. Use
      different people and places across scenes instead of the same two people for the whole film.
      No single noun (a person, a prop, a place) may appear in more than a third of the shots;
    - natural real-time speed. Never write slow motion, "slowly", "gently", "steady", "lingering",
      "static" or "calm" for the pace; use "quick", "brisk", "snap", "sweeps", "tracks" when it fits;
    - describe only what the camera sees. NEVER include on-screen text, captions, logos, brand
      names to be read, subtitles, voiceover or music;
    - people, places and props that recur must be described with the same words every time.
  Never mention the editor, post-production, graphics, overlays or magnifying-glass effects in a
  shot: shots are sent to Seedance, which should read only a description of footage.
  Seedance also draws garbled gibberish on anything covered in writing, so NEVER make a close-up
  of a notebook, notepad, whiteboard, printed page, spreadsheet, sign, or a phone or laptop screen
  the subject of a shot. Show the person's hands, face or reaction instead, or the object from
  behind or far out of focus, or use another prop with no writing (a calculator is fine only
  from a distance; coins, parcels, a street, a shop window, a handshake are safe).
  Seedance cannot render legible interface text, charts or logos. Where the script wants a
  screen, report, dashboard or end card, write the footage the editor will cover instead: for
  example a laptop whose screen is blurred or angled away and glowing softly, or a calm
  office shot. Never describe readable screen content, and never say a screen "shows" or
  "displays" an interface, report, dashboard, chart or data: say only that it glows softly and
  is out of focus or angled away. Wrong: "the screen clearly shows an analytics interface".
  Right: "the laptop screen glows softly, out of focus".
  THINK LIKE A VIDEO EDITOR ABOUT HOW LONG THINGS STAY ON SCREEN. A headline or text card holds
  2-3 seconds, a screen mock-up 3-6 seconds, and an end card, logo or call-to-action only 2-4
  seconds, always over the words being spoken at that moment, never over a whole paragraph.
- "closing_card": for a closing scene with an end card, logo, offer or call-to-action, set this
  to {"line": the exact LAST sentence of that scene's voiceover that the end card sits on (for
  example "Book your free consultation today."), or "" when nothing is spoken
  in that scene, "note": how the editor builds the card (layout, colours, logo, button, exact
  copy from the script)}. The system then splits the scene itself: the lead-in sentences stay
  as the scene (so "shots" must describe real, relevant footage for the lead-in only, NOT an end
  card, laptop summary or empty background), and the system makes the short call-to-action part
  with an empty background. If a visible person speaks that last line to camera ("speech":
  "on_camera"), the system keeps that person on screen and only lays the card over the last
  seconds. Never put the script's laptop mock-up, logo, button or card layout into "shots".
  Use null when the scene has no end card.
- "voiceover": the exact spoken line(s) for that scene, word for word from the script. Empty if
  nothing is spoken.
- "speech": "on_camera" if a visible person speaks the line to camera or to another person
  (testimonial, dialogue); "voiceover" if it is off-camera narration; "none" if nothing is spoken.
- "on_screen_text": the exact on-screen text lines from the script (the editor/finishing adds
  them). The script may label them "On-screen text", "Text on screen", "Title card", and so on.
- "edit_inserts": what the editor lays over this scene. One entry for each screen mock-up, data
  visual, title card, logo or end card, supplied footage, or anything needing exact text/UI:
  {"starts_at_seconds": offset inside the scene, "duration_seconds": n, "kind": "screen" |
  "text card" | "end card" | "footage" | "graphic", "note": what to build, with the script's
  colours, labels and any "do not imply..." caution}. Empty list if the scene needs none.
  "starts_at_seconds" + "duration_seconds" must fit inside the scene's own length; give each
  insert at least 2 seconds and do not overlap inserts of the same kind.
  For every insert of kind "screen" or "graphic" ALSO write "image_prompt": a complete, self-contained
  prompt for an AI image model (GPT Image 2 or Seedream) that draws the finished full-frame picture
  the viewer will see for those seconds: what is shown, its layout and colours, and the exact SHORT
  text, numbers or labels that must appear (a few words each, in correct English). Use realistic
  generic sample content and never real brand names. NEVER put a logo, wordmark, slogan or the
  client's brand or company name in an image_prompt (the real logo is added afterwards from the brand
  kit), and do not ask for a logo or brand name on screens, signs or clothing. Example: "Photoreal close-up of a laptop screen
  showing a clean analytics table with three columns headed Search Term, Clicks and Spend; green
  highlight on rows with purchase-intent terms, red on irrelevant ones; a small running total reading
  $412 in the corner; soft office background." Leave "image_prompt" out for every other kind. These
  images replace what Seedance cannot draw, so the footage underneath stays safe and writing-free.
- "reason": one short sentence on how you split Seedance vs editing for this scene.

TIMING
Use durations written in the script ("duration_source": "script"). If the script gives none, set
"duration_source": "estimated"; the scene's length then follows its voiceover at about
2.5 spoken words per second. A scene with no voiceover and no stated length is 3-5 seconds.
No scene may be longer than the clip limit in the context; split a longer scene into two scenes.
If the script states an overall length (for example "a 20 second ad"), the scene durations must
add up to it; give each scene a whole-number share and use "duration_source": "script".
Always fill "duration_seconds" with a whole number.

VOICE
The film's voice is always Australian English; do not change the accent or language. Fill the
top-level "voice" ONLY from what the script itself says: "gender": "female" or "male" if the
script names the voice's gender, else "". "speakers": the number of distinct speaking voices in
the script (1 if a single narrator or presenter). Never guess a gender the script does not state.

Respond with ONLY valid JSON, no markdown fences:
{
  "title": "short project title",
  "global_style": "one paragraph: look, colour grade, lighting, lens language shared by every scene; energetic and cinematic, never slow or static",
  "voice": {"gender": "female" | "male" | "", "speakers": 1},
  "scenes": [
    {
      "title": "The hook",
      "duration_seconds": 8,
      "duration_source": "script" | "estimated",
      "voiceover": "exact spoken line",
      "speech": "on_camera" | "voiceover" | "none",
      "shots": [{"seconds": 3, "description": "..."}, {"seconds": 3, "description": "..."}, {"seconds": 3, "description": "..."}],
      "on_screen_text": ["..."],
      "edit_inserts": [{"starts_at_seconds": 4, "duration_seconds": 4, "kind": "screen", "note": "...", "image_prompt": "..."}],
      "closing_card": null,
      "reason": "..."
    }
  ]
}
"""

# What Seedance is asked to generate under an end card / call to action. Written by the code, not
# the model, so the background is always genuinely empty for the logo and text added in editing.
EMPTY_BACKGROUND = (
    "A softly lit, plain studio background with a slow, gentle drift of light and soft depth. "
    "Completely empty: no people, no laptop, no desk, no objects, no writing."
)


# ── reading the script ──────────────────────────────────────────────────────


def _docx_text(content: bytes) -> str:
    from docx import Document  # python-docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(io.BytesIO(content))
    lines: list[str] = []
    # Walk the body in document order so tables stay between the paragraphs around them.
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = Paragraph(child, document).text.strip()
            if text:
                lines.append(text)
        elif tag == "tbl":
            table = Table(child, document)
            for row in table.rows:
                cells: list[str] = []
                for cell in row.cells:
                    value = " ".join(cell.text.split())
                    if value and (not cells or cells[-1] != value):  # merged cells repeat
                        cells.append(value)
                if cells:
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


def extract_script_text(content: bytes, filename: str) -> str:
    """Return plain script text from a .docx / .txt / .md upload."""
    name = (filename or "").lower()
    if name.endswith(".docx"):
        try:
            text = _docx_text(content)
        except Exception as exc:  # corrupt / not really a docx
            raise ValueError("Could not read this Word file. Save it as .docx and try again.") from exc
    elif name.endswith((".txt", ".md")):
        text = content.decode("utf-8", errors="replace")
    elif name.endswith(".doc"):
        raise ValueError("Old .doc files are not supported. Save the script as .docx and upload again.")
    else:
        raise ValueError("Upload the script as a .docx, .txt or .md file, or paste the text.")
    text = text.replace("\r\n", "\n").strip()
    if not text:
        raise ValueError("The script file is empty.")
    return text


def script_plan_model(chat_model: str | None) -> str:
    """Model used to plan a script: GPT-4.1 unless the user picked another model explicitly.

    Always an allowed catalog slug (a stale or unknown value falls back safely).
    """
    from app.services.prompt_llm_catalog import resolve_prompt_llm_model

    picked = (chat_model or "").strip()
    return resolve_prompt_llm_model(picked if picked and picked != "auto" else SCRIPT_PLAN_DEFAULT_MODEL)


# ── the voice the script asks for ───────────────────────────────────────────

_VOICE_CONTEXT = re.compile(r"(?i)\b(voice|voiceover|voice-over|narrat\w*|presenter|speaker|spoken)\b")
_FEMALE = re.compile(r"(?i)\b(female|woman|women|girl|feminine)\b")
_MALE = re.compile(r"(?i)\b(male|man|men|boy|masculine)\b")
# Every film uses an Australian English voice. The script can choose male or female; it cannot
# change the accent or the language.
VOICE_ACCENT = "Australian English"


def detect_voice(script_text: str) -> dict[str, Any]:
    """Voice for the film: always Australian English; male or female only if the script says so.

    Only lines that talk about the voice are read for gender, so a "woman" in a visual direction
    is not mistaken for the narrator.
    """
    gender: set[str] = set()
    for line in re.split(r"[\n.;]+", script_text or ""):
        if not _VOICE_CONTEXT.search(line):
            continue
        if re.search(r'["“”]', line) and not re.search(r"(?i)\b(voice|narrat\w*)\b[^\"“”]{0,60}[:\-–]", line):
            # Looks like a quoted spoken line, not a description of the voice.
            continue
        if _FEMALE.search(line):
            gender.add("female")
        if _MALE.search(_FEMALE.sub("", line)):
            gender.add("male")
    warnings: list[str] = []
    chosen_gender = next(iter(gender)) if len(gender) == 1 else ""
    if len(gender) > 1:
        warnings.append("The script mentions both a male and a female voice; no voice gender was locked. Please check it.")
    return _voice_result(chosen_gender, warnings)


def _voice_result(gender: str, warnings: list[str]) -> dict[str, Any]:
    base = f"{VOICE_ACCENT} {gender} voice" if gender else f"{VOICE_ACCENT} voice"
    return {
        "gender": gender,
        "accent": VOICE_ACCENT,
        # "script" only when the script chose male/female; the accent is always fixed by the app.
        "source": "script" if gender else "default",
        "base_line": base,
        # Final wording (narration vs on-camera) is set once the scenes are known.
        "prompt_line": f"{base}, natural delivery at a steady pace.",
        "warnings": warnings,
    }


def _voice_from_model(raw_voice: Any) -> tuple[str, int]:
    """The planner's reading of the script's voice: male/female and the number of speakers."""
    if not isinstance(raw_voice, dict):
        return "", 1
    gender = _text(raw_voice.get("gender"), 10).lower()
    gender = gender if gender in {"female", "male"} else ""
    try:
        speakers = int(raw_voice.get("speakers") or 1)
    except (TypeError, ValueError):
        speakers = 1
    return gender, max(1, min(speakers, 12))


# ── cleaning the model's answer ─────────────────────────────────────────────


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            value = json.loads(fence.group(1).strip())
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _clock(seconds: float) -> str:
    return f"{seconds:g}"


def _spoken(value: str) -> str:
    """One line, with straight double quotes removed so the existing line parser stays intact."""
    return " ".join(str(value or "").replace('"', "'").replace("“", "'").replace("”", "'").split())


# "no readable text or logos anywhere", "not legible", "unreadable": a negated clause is safe.
_NEGATED_TEXT = re.compile(
    # a negation runs to the end of its clause: a comma, full stop, semicolon, or " and " / " but " / " then "
    r"(?i)\b(?:no|not|never|without|nothing)\b(?:(?! and | but | then )[^.;,]){0,100}|\bunreadable\b|\billegible\b"
)
_RISKY_FOOTAGE = re.compile(
    r"(?i)\b(logos?|dashboards?|interfaces?|search[- ]term report|charts?|graphs?|captions?|subtitles?|headlines?|branding|"
    r"labell?ed|lettering|signage|the words?|notebooks?|notepads?|whiteboards?|printouts?|printed (?:page|report|document)s?|"
    r"spreadsheets?|phone screen|smartphone screen)\b"
)


# Things Seedance is known to draw as garbled gibberish. The planner is told not to use them; when one
# still slips through, it is swapped for a safe alternative here, so the prompt is right without the
# user having to reword anything. Phrases the model wrote as NEGATIONS ("no logos") are left alone.
_SAFE_SUBSTITUTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b(?:labell?ed|titled|marked|reading|reads)\s+['\"“‘][^'\"”’]{1,80}['\"”’]"), ""),
    (re.compile(r"(?i)\bthe words?\s+['\"“‘][^'\"”’]{1,160}['\"”’](?:\s+and\s+['\"“‘][^'\"”’]{1,80}['\"”’])*"), "the paper"),
    (re.compile(r"(?i)\bthe words?\b"), "the paper"),
    (re.compile(r"(?i)\bnote(?:book|pad)s?\b"), "folder"),
    (re.compile(r"(?i)\bwhiteboards?\b"), "glass wall"),
    (re.compile(r"(?i)\bspreadsheets?\b"), "stack of papers"),
    (re.compile(r"(?i)\bsearch[- ]term reports?\b"), "papers"),
    (re.compile(r"(?i)\bprintouts?\b"), "papers"),
    (re.compile(r"(?i)\bprinted (?:page|report|document)s?\b"), "papers"),
    (re.compile(r"(?i)\b(?:smart)?phone screen\b"), "phone held at an angle, screen turned away"),
    (re.compile(r"(?i)\bdashboards?\b"), "glowing screen, out of focus"),
    (re.compile(r"(?i)\binterfaces?\b"), "glowing screen"),
    (re.compile(r"(?i)\b(?:pie|bar|line)\s+(?:charts?|graphs?)\b"), "coloured shapes"),
    (re.compile(r"(?i)\b(?:charts?|graphs?)\b"), "papers"),
    (re.compile(r"(?i)\blogos?\b"), "plain surface"),
    (re.compile(r"(?i)\bbranding\b"), "plain surface"),
    (re.compile(r"(?i)\b(?:captions?|subtitles?|headlines?)\b"), ""),
    (re.compile(r"(?i)\b(?:lettering|signage)\b"), "plain panel"),
    (re.compile(r"(?i)\blabell?ed\b"), "marked"),
)


def _substitute_unsafe(text: str) -> str:
    for pattern, replacement in _SAFE_SUBSTITUTIONS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", text))  # no stray space inside brackets
    return re.sub(r"\s+([,.;:])", r"\1", text).strip()


def sanitize_footage_text(text: str) -> str:
    """Swap words that make Seedance draw garbled writing for safe alternatives (idempotent)."""
    def keep_spacing(segment: str) -> str:
        # _substitute_unsafe trims its ends; put the original spacing back so neighbouring words never fuse
        core = _substitute_unsafe(segment)
        if not core:
            return segment[:1] if segment[:1].isspace() else ""
        lead = segment[: len(segment) - len(segment.lstrip())]
        trail = segment[len(segment.rstrip()) :]
        return lead + core + trail

    text = text or ""
    out, position = [], 0
    for negated in _NEGATED_TEXT.finditer(text):
        out.append(keep_spacing(text[position : negated.start()]))
        out.append(negated.group(0))
        position = negated.end()
    out.append(keep_spacing(text[position:]))
    return re.sub(r"[ \t]{2,}", " ", "".join(out)).strip()


def _sanitize_rows(rows: list[Any]) -> list[Any]:
    cleaned: list[Any] = []
    for row in rows:
        if isinstance(row, dict):
            row = dict(row)
            if isinstance(row.get("shots"), list):
                row["shots"] = [
                    {**shot, "description": sanitize_footage_text(str(shot.get("description") or ""))} if isinstance(shot, dict) else shot
                    for shot in row["shots"]
                ]
            if isinstance(row.get("visual_direction"), str):
                row["visual_direction"] = sanitize_footage_text(row["visual_direction"])
        cleaned.append(row)
    return cleaned


def _risky_footage_words(text: str) -> list[str]:
    """Words in a footage description that invite Seedance to draw readable text or UI."""
    cleaned = _NEGATED_TEXT.sub(" ", text or "")
    found: list[str] = []
    for match in _RISKY_FOOTAGE.finditer(cleaned):
        word = match.group(1).lower()
        if word not in found:
            found.append(word)
    return found


def _scene_seconds(voiceover: str) -> int:
    words = len(voiceover.split())
    return max(MIN_SCENE_SECONDS, int(math.ceil(words / WORDS_PER_SECOND + 0.3)))


# Footage for the lead-in sentence(s) must not be the end card itself. If the planner described the
# card's layout there anyway, the lead-in simply carries on from the previous scene.
_END_CARD_WORDS = re.compile(
    r"(?i)\b(logos?|branding|end[- ]card|call[- ]to[- ]action|cta|buttons?|dashboards?|interfaces?|"
    r"search[- ]term report|charts?|graphs?|captions?|subtitles?|headlines?|summary (?:screen|page)|audit summary)\b"
)
LEAD_IN_CONTINUATION = (
    "Continue directly from the previous scene with the same people, setting and lighting. A calm, "
    "confident closing moment: the person looks up and settles back, relaxed and reassuring. Screens stay "
    "out of view or softly out of focus, and nothing with writing is visible."
)


def _clean_shots(raw: Any) -> list[tuple[str, float]]:
    """(description, planned seconds) for each usable shot the planner wrote."""
    shots: list[tuple[str, float]] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            description = _text(item.get("description"), 700)
            if description:
                shots.append((description, _number(item.get("seconds")) or 0.0))
    return shots


def _shots_text(row: dict[str, Any]) -> str:
    """All of a scene's footage text (shot list, else the single description) for keyword checks."""
    shots = _clean_shots(row.get("shots"))
    return " ".join(d for d, _ in shots) if shots else _text(row.get("visual_direction"), 4000)


def _build_shots(raw: Any, duration: int) -> list[dict[str, Any]] | None:
    """Fit the planner's shot list to the scene length: whole seconds, none under 2s, sum == duration.

    The planner's own proportions are kept. If it wrote more shots than fit, the extras are dropped
    (never merged into a longer, slower shot). None when there is no usable shot list.
    """
    items = _clean_shots(raw)
    if not items:
        return None
    count = max(1, min(len(items), duration // MIN_SHOT_SECONDS, MAX_SHOTS))
    items = items[:count]
    weights = [w if w > 0 else duration / count for _, w in items]
    total = sum(weights)
    seconds = [max(MIN_SHOT_SECONDS if duration >= MIN_SHOT_SECONDS * count else 1, int(round(w / total * duration))) for w in weights]
    diff, guard = duration - sum(seconds), 0
    while diff != 0 and guard < 500:  # absorb rounding from the last shot backwards
        index = len(seconds) - 1 - (guard % len(seconds))
        if diff > 0:
            seconds[index] += 1
            diff -= 1
        elif seconds[index] > MIN_SHOT_SECONDS:
            seconds[index] -= 1
            diff += 1
        guard += 1
    return [{"seconds": s, "description": d} for (d, _), s in zip(items, seconds)]


_GENERIC_SHOT_WORDS = frozenset(
    "shot shots close medium wide overhead macro angle frame camera zoom cutaway focus focused focusing softly "
    "blurred glows glowing screen angled quick sequence while their there where which about across along around "
    "behind between through towards toward next after before above below beside under over into onto from with "
    "without that this those these have having being more most other another same each every very just then than "
    "also still pushes slowly".split()
)
REPEAT_SHARE = 0.45  # a noun in more than this share of shots reads as the same picture again
REPEAT_MIN_COUNT = 4


def _repetition(scenes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The noun that shows up in too many shots (a person, prop or place), or None if the cut varies.

    Words the voiceover itself uses are the film's topic, not a lazy repeat, so they are ignored.
    """
    shots = [s["description"] for scene in scenes for s in scene.get("shots") or []]
    if len(shots) < REPEAT_MIN_COUNT + 1:
        return None
    topic = {w[:5] for scene in scenes for w in re.findall(r"[a-z]{5,}", scene["voiceover"].lower())}
    counts: dict[str, int] = {}
    for text in shots:
        for word in {w for w in re.findall(r"[a-z]{5,}", text.lower()) if w not in _GENERIC_SHOT_WORDS and w[:5] not in topic}:
            counts[word] = counts.get(word, 0) + 1
    if not counts:
        return None
    word, count = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    if count >= REPEAT_MIN_COUNT and count / len(shots) > REPEAT_SHARE:
        return {"word": word, "count": count, "total": len(shots)}
    return None


def _end_card_covers_most(row: dict[str, Any]) -> bool:
    """True when the planner's own end-card insert fills most of the scene."""
    duration = _number(row.get("duration_seconds"))
    for item in row.get("edit_inserts") if isinstance(row.get("edit_inserts"), list) else []:
        if isinstance(item, dict) and _text(item.get("kind"), 30).lower() == "end card":
            held = _number(item.get("duration_seconds"))
            if duration and held and held >= 0.7 * duration:
                return True
    return False


def _expand_closing_cards(rows: list[Any]) -> list[Any]:
    """Split a closing scene so the end card only holds over the call-to-action sentence.

    The planner names the sentence the card sits on (``closing_card.line``). The scene's earlier
    sentences stay as the scene with the planner's real footage; the call to action becomes its own
    short scene whose footage is always ``EMPTY_BACKGROUND`` (written here, not by the model) and
    whose end-card insert covers all of it. The voiceover stays continuous across the two.
    A scene whose voiceover does not end with that sentence is left exactly as planned.
    """
    expanded: list[Any] = []
    for row in rows:
        card = row.get("closing_card") if isinstance(row, dict) else None
        line = _spoken(_text(card.get("line"), 600)) if isinstance(card, dict) else ""
        voice = _spoken(_text(row.get("voiceover"), 1500)) if isinstance(row, dict) else ""
        if isinstance(row, dict):
            card_note = (_text(card.get("note"), 1200) if isinstance(card, dict) else "") or (
                "Build the end card: logo, offer text and call to action."
            )
            kept = [
                i
                for i in (row.get("edit_inserts") if isinstance(row.get("edit_inserts"), list) else [])
                if isinstance(i, dict) and _text(i.get("kind"), 30).lower() != "end card"
            ]
            # A visible person says the closing line to camera: keep them on screen and lay the
            # card over the last seconds only, rather than replacing them with an empty background.
            if isinstance(card, dict) and voice and _text(row.get("speech"), 12).lower() == "on_camera":
                expanded.append(
                    {
                        **row,
                        "edit_inserts": [
                            *kept,
                            {"anchor": "end", "duration_seconds": END_CARD_DEFAULT_SECONDS, "kind": "end card", "note": card_note},
                        ],
                        "closing_card": None,
                    }
                )
                continue
            # A silent scene that is wholly an end card: nothing to show but an empty background.
            if not voice and (isinstance(card, dict) or _end_card_covers_most(row)):
                expanded.append(
                    {
                        **row,
                        "visual_direction": EMPTY_BACKGROUND,
                        "shots": None,
                        "speech": "none",
                        "edit_inserts": [
                            *kept,
                            {"starts_at_seconds": 0, "duration_seconds": _number(row.get("duration_seconds")) or MIN_SCENE_SECONDS, "kind": "end card", "note": card_note},
                        ],
                        "closing_card": None,
                    }
                )
                continue
        core_voice, core_line = voice.rstrip(" .!?"), line.rstrip(" .!?")
        if not core_line or not core_voice.lower().endswith(core_line.lower()):
            expanded.append(row)
            continue

        cut = len(core_voice) - len(core_line)
        lead, cta_voice = voice[:cut].strip(), voice[cut:].strip()
        note = _text(card.get("note"), 1200) or "Build the end card: logo, offer text and call to action."
        title = _text(row.get("title"), 80) or "Closing"
        scripted = _text(row.get("duration_source"), 20).lower() == "script"
        total = _number(row.get("duration_seconds"))
        source = "script" if scripted and total else "estimated"
        other_inserts = [
            i
            for i in (row.get("edit_inserts") if isinstance(row.get("edit_inserts"), list) else [])
            if isinstance(i, dict) and _text(i.get("kind"), 30).lower() != "end card"
        ]

        if lead:
            cta_seconds = max(MIN_SCENE_SECONDS, _scene_seconds(cta_voice))
            lead_seconds = max(MIN_SCENE_SECONDS, int(round(total - cta_seconds))) if source == "script" else _scene_seconds(lead)
            lead_text = _shots_text(row)
            lead_visual, lead_shots = _text(row.get("visual_direction"), 4000), row.get("shots")
            lead_reason = _text(row.get("reason"), 300)
            if not lead_text or _END_CARD_WORDS.search(_NEGATED_TEXT.sub(" ", lead_text)):
                lead_visual, lead_shots = LEAD_IN_CONTINUATION, None
                lead_reason = "Lead-in carries on from the previous scene; the end card is only on the last line."
            expanded.append(
                {
                    **row,
                    "voiceover": lead,
                    "duration_seconds": lead_seconds,
                    "duration_source": source,
                    "visual_direction": lead_visual,
                    "shots": lead_shots,
                    "reason": lead_reason,
                    "on_screen_text": [],
                    "edit_inserts": other_inserts,
                    "closing_card": None,
                }
            )
            cta_title, cta_inserts = f"{title} - call to action", []
        else:  # the whole scene is the call to action
            cta_seconds = int(round(total)) if source == "script" else max(MIN_SCENE_SECONDS, _scene_seconds(cta_voice))
            cta_title, cta_inserts = title, other_inserts

        expanded.append(
            {
                "title": cta_title,
                "duration_seconds": cta_seconds,
                "duration_source": source,
                "voiceover": cta_voice,
                "visual_direction": EMPTY_BACKGROUND,
                "on_screen_text": row.get("on_screen_text") if isinstance(row.get("on_screen_text"), list) else [],
                "edit_inserts": [
                    *cta_inserts,
                    {"starts_at_seconds": 0, "duration_seconds": cta_seconds, "kind": "end card", "note": note},
                ],
                "reason": _text(row.get("reason"), 300) or "End card holds over the call to action on an empty background.",
                "closing_card": None,
            }
        )
    return expanded


# ── validation ──────────────────────────────────────────────────────────────


_SECONDS_WORD = r"(?:s|secs?|seconds?)"
_CLOCK_OR_NUMBER = r"(\d{1,2}:\d{2}(?:\.\d+)?|\d+(?:\.\d+)?)"


def _clock_seconds(value: str) -> float:
    if ":" in value:
        minutes, seconds = value.split(":", 1)
        return int(minutes) * 60 + float(seconds)
    return float(value)


def _duration_evidence(script_text: str) -> set[int]:
    """Every duration the script itself writes: "8s", "8 seconds", "0-9 SECONDS", "0:00-0:09"."""
    found: set[int] = set()
    text = script_text or ""
    for match in re.finditer(rf"(?i)\b(\d+(?:\.\d+)?)\s*{_SECONDS_WORD}\b", text):
        found.add(int(round(float(match.group(1)))))
    for match in re.finditer(rf"(?i){_CLOCK_OR_NUMBER}\s*{_SECONDS_WORD}?\s*[–—-]\s*{_CLOCK_OR_NUMBER}", text):
        length = _clock_seconds(match.group(2)) - _clock_seconds(match.group(1))
        if 0 < length <= 600:
            found.add(int(round(length)))
    return found


def _verify_scripted_durations(rows: list[Any], script_text: str) -> list[Any]:
    """A duration may only be treated as the script's own if the script really says it.

    The planner is told to use durations written in the script, but it can claim "script" for numbers
    it invented (often too short for the voiceover). A claim is trusted when that length appears in
    the script, or when the claimed lengths add up to the total the script states. Otherwise the scene
    falls back to a length worked out from its voiceover.
    """
    if not (script_text or "").strip():
        return rows
    evidence = _duration_evidence(script_text)
    stated = _stated_total_seconds(script_text)
    claimed = [
        _number(r.get("duration_seconds"))
        for r in rows
        if isinstance(r, dict) and _text(r.get("duration_source"), 20).lower() == "script"
    ]
    sums_to_total = bool(stated) and all(claimed) and abs(sum(c or 0 for c in claimed) - stated) <= 1
    checked: list[Any] = []
    for row in rows:
        if isinstance(row, dict) and _text(row.get("duration_source"), 20).lower() == "script" and not sums_to_total:
            seconds = _number(row.get("duration_seconds"))
            if seconds is None or int(round(seconds)) not in evidence:
                row = {**row, "duration_source": "estimated"}
        checked.append(row)
    return checked


def normalize_plan(raw: dict[str, Any], *, clip_cap: int, script_text: str = "", sanitize: bool = False) -> dict[str, Any]:
    """Validate the planner's JSON into a safe timeline plus an editor to-do list.

    - Scene durations are whole seconds; start/end are rebuilt so the timeline has no gaps.
    - When the script gave no durations, each scene's length is recomputed from its voiceover.
    - A scene under Seedance's 4s minimum is lengthened to 4s and flagged; one over the clip
      limit is flagged (the model is told to split those, so this is a safety net).
    - A scene without footage direction cannot be generated, so it is reported and given a
      neutral placeholder instead of an empty prompt.
    """
    warnings: list[str] = []
    rows = raw.get("scenes") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("The planner returned no scenes. Try again or shorten the script.")

    if sanitize:
        rows = _sanitize_rows(rows)
    rows = _expand_closing_cards(_verify_scripted_durations(rows, script_text))

    scenes: list[dict[str, Any]] = []
    risky_shots: list[dict[str, Any]] = []
    for position, row in enumerate(rows[:MAX_SCENES], start=1):
        if not isinstance(row, dict):
            continue
        title = _text(row.get("title"), 80) or f"Scene {position}"
        voiceover = _spoken(_text(row.get("voiceover"), 1500))
        source = "script" if _text(row.get("duration_source"), 20).lower() == "script" else "estimated"

        seconds = _number(row.get("duration_seconds"))
        if source == "estimated" and voiceover:
            seconds = float(_scene_seconds(voiceover))
        if seconds is None:
            warnings.append(f'"{title}" had no duration in the plan; set to {MIN_SCENE_SECONDS}s. Please check it.')
            seconds = float(MIN_SCENE_SECONDS)
        duration = max(1, int(round(seconds)))
        if duration < MIN_SCENE_SECONDS:
            warnings.append(
                f'"{title}" is {duration}s but Seedance needs at least {MIN_SCENE_SECONDS}s, '
                f"so it will be generated at {MIN_SCENE_SECONDS}s. Trim it in editing."
            )
            duration = MIN_SCENE_SECONDS
        if duration > clip_cap:
            warnings.append(
                f'"{title}" is {duration}s, longer than one Seedance clip ({clip_cap}s). '
                "Split it into two scenes in the script."
            )

        shots = _build_shots(row.get("shots"), duration)
        for number, shot in enumerate(shots or [], start=1):
            found = _risky_footage_words(shot["description"])
            if found:
                risky_shots.append({"scene": title, "shot": number, "words": found})
        if shots:
            visual = "\n".join(f"Shot {i} ({s['seconds']}s): {s['description']}" for i, s in enumerate(shots, start=1))
            longest = max(s["seconds"] for s in shots)
            if longest > LONG_SHOT_SECONDS:
                warnings.append(
                    f'"{title}" has a {longest}s single shot. Shots of 2-4s feel faster; add more shots for a livelier cut.'
                )
        else:
            visual = _text(row.get("visual_direction"), 4000)
            if not visual:
                visual = "Well-lit establishing shot that fits the surrounding scenes; no readable text."
                warnings.append(f'"{title}" had no footage direction; a neutral placeholder shot was used. Please edit it.')
            elif duration > LONG_SHOT_SECONDS and visual not in (EMPTY_BACKGROUND, LEAD_IN_CONTINUATION):
                warnings.append(
                    f'"{title}" is one {duration}s shot with no cuts, which tends to look slow. Break it into shots of 2-4s.'
                )

        risky = _risky_footage_words(visual)
        if risky:
            warnings.append(
                f'"{title}": the footage description mentions {", ".join(repr(w) for w in risky)}. '
                "Seedance may draw garbled readable text there. Reword it so screens stay blurred or angled away."
            )

        text_lines = row.get("on_screen_text") if isinstance(row.get("on_screen_text"), list) else []
        inserts_raw = row.get("edit_inserts") if isinstance(row.get("edit_inserts"), list) else []
        inserts: list[dict[str, Any]] = []
        for item in inserts_raw[:20]:
            if not isinstance(item, dict):
                continue
            note = _text(item.get("note"), 1200)
            if not note:
                continue
            length = _number(item.get("duration_seconds"))
            if item.get("anchor") == "end":  # held over the last seconds, wherever the scene ends
                length = min(length or float(END_CARD_DEFAULT_SECONDS), float(duration))
                offset = float(duration) - length
            else:
                offset = _number(item.get("starts_at_seconds")) or 0.0
                length = min(length or max(float(duration) - offset, 0.5), float(duration))
                # keep the planned length: if it would overflow the scene, start it earlier
                offset = min(max(0.0, offset), float(duration) - length)
            kind = _text(item.get("kind"), 30).lower() or "graphic"
            image_prompt = _text(item.get("image_prompt"), MAX_STILL_PROMPT_CHARS) if kind in STILL_KINDS else ""
            if image_prompt:
                # a still is shown for 2-6 seconds: long enough to read, short enough to stay lively
                length = min(max(length, MIN_STILL_SECONDS), MAX_STILL_SECONDS, float(duration))
                offset = min(offset, float(duration) - length)
            inserts.append(
                {
                    "kind": kind,
                    "offset": round(offset, 2),
                    "length": round(max(length, 0.5), 2),
                    "note": note,
                    "image_prompt": image_prompt,
                }
            )

        speech = _text(row.get("speech"), 12).lower()
        if speech not in {"on_camera", "voiceover", "none"}:
            speech = "voiceover" if voiceover else "none"
        if not voiceover:
            speech = "none"

        need = len(voiceover.split()) / WORDS_PER_SECOND
        if voiceover and need > duration + 0.5:
            warnings.append(
                f'"{title}": the spoken line needs about {need:.0f}s but the scene is {duration}s, so the voice may be '
                "rushed or cut off. Lengthen the scene or shorten the line."
            )

        scenes.append(
            {
                "title": title,
                "duration_seconds": duration,
                "duration_source": source,
                "speech": speech,
                "voiceover": voiceover,
                "shots": shots or [],
                "visual_direction": visual,
                "on_screen_text": [_text(t, 160) for t in text_lines[:12] if _text(t, 160)],
                "reason": _text(row.get("reason"), 300),
                "_inserts": inserts,
            }
        )

    if not scenes:
        raise ValueError("The planner returned no usable scenes. Try again.")

    cursor = 0.0
    edit_list: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        scene["index"] = index
        scene["start"] = round(cursor, 2)
        cursor += scene["duration_seconds"]
        scene["end"] = round(cursor, 2)
        inserts = scene.pop("_inserts")
        for insert in inserts:
            start = round(scene["start"] + insert["offset"], 2)
            edit_list.append(
                {
                    "scene": index,
                    "scene_title": scene["title"],
                    "start": start,
                    "end": round(min(start + insert["length"], scene["end"]), 2),
                    "kind": insert["kind"],
                    "note": insert["note"],
                    "image_prompt": insert["image_prompt"],
                }
            )
        # Text is added by hand, so the editor always gets the exact lines and the scene window,
        # even when the planner did not list a text card for this scene.
        if scene["on_screen_text"] and not any(i["kind"] in {"text card", "text"} for i in inserts):
            lines = " / ".join(f"“{t}”" for t in scene["on_screen_text"])
            edit_list.append(
                {
                    "scene": index,
                    "scene_title": scene["title"],
                    "start": scene["start"],
                    "end": scene["end"],
                    "kind": "text",
                    "note": f"Add this exact on-screen text, held about 2-3 seconds where the line is spoken: {lines}",
                    "image_prompt": "",
                }
            )
    edit_list.sort(key=lambda item: (item["start"], item["end"]))
    for item in edit_list:
        held = item["end"] - item["start"]
        if item["kind"] == "end card" and held > MAX_END_CARD_SECONDS:
            warnings.append(
                f'The end card is on screen for {held:g}s (scene {item["scene"]}). End cards usually hold 2-4s over the '
                "last words. Split the scene so only the call-to-action line sits on the empty background."
            )

    return {
        "title": _text(raw.get("title"), 120),
        "global_style": _text(raw.get("global_style"), 1500),
        "scenes": scenes,
        "edit_list": edit_list,
        "stills": _stills_from_edit_list(edit_list),
        "total_seconds": int(round(cursor)),
        "edit_count": len(edit_list),
        "risky_shots": risky_shots,
        "warnings": warnings,
    }


# ── the canonical prompt for the existing pipeline ──────────────────────────


def compile_canonical_prompt(
    plan: dict[str, Any],
    voice: dict[str, Any] | None = None,
    *,
    include_on_screen_text: bool = False,
) -> str:
    """Write the plan as the sectioned timed prompt the existing pipeline already parses.

    ``include_on_screen_text`` is off by default: the existing pipeline reads every
    ``ON-SCREEN TEXT:`` block and burns it into the finished video, but this workflow adds text
    and logos by hand, so the blocks are left out unless asked for.
    """
    lines: list[str] = []
    title = (plan.get("title") or "").strip()
    total = int(plan.get("total_seconds") or 0)
    lines.append((title or "Script film").upper() + (f" — {total} SECOND FILM" if total else ""))
    voice_line = (voice or {}).get("prompt_line") or ""
    if voice_line:
        lines.append(voice_line)
    style = (plan.get("global_style") or "").strip()
    if style:
        lines.append(f"Look and feel for every scene: {style}")
    lines.append(
        "Seedance generates continuous footage for every scene. Text, logos, graphics, screens and end "
        "cards are added later in editing, so never show readable text, interface copy or logos in the footage."
    )
    lines.append(
        "Pace: energetic, natural real-time speed, never slow motion. Follow each scene's shot list and cut to a "
        "new shot at every shot change, so the film moves like a professionally edited ad."
    )
    if any(scene["voiceover"] for scene in plan["scenes"]):
        # Seedance tends to open with a few silent seconds unless told otherwise. Avoid the words
        # "exact", "following" and "this" here: the system's voiceover reader treats those as the start
        # of a spoken line.
        lines.append(
            "Audio: speech starts on the very first frame (0:00) with no silent lead-in, and each scene's line begins "
            "the instant its scene begins, with no pause between scenes."
        )
    lines.append("")
    for scene in plan["scenes"]:
        a, b = _clock(scene["start"]), _clock(scene["end"])
        lines.append(f"SCENE {scene['index']} - {scene['title'].upper()} | {a}-{b} SECONDS")
        if scene["voiceover"]:
            who = "the person starts speaking" if scene.get("speech") == "on_camera" else "the voice starts"
            lines.append(f"SPEECH CUE: {who} on the first frame of this scene, over Shot 1, with no silent lead-in.")
        lines.append("VISUAL DIRECTION:")
        lines.append(scene["visual_direction"])
        # Voiceover goes BEFORE the on-screen text block: the existing caption reader takes
        # every line after "ON-SCREEN TEXT:" up to the separator, so a voiceover line placed
        # after it would be burned into the video as a caption.
        if scene["voiceover"]:
            lines.append(f'Voiceover, {a}-{b} seconds: "{scene["voiceover"]}"')
        if include_on_screen_text and scene["on_screen_text"]:
            lines.append("ON-SCREEN TEXT:")
            lines.extend(f"“{t}”" for t in scene["on_screen_text"])
        lines.append("----------------")
    return "\n".join(lines).rstrip("-\n ") + "\n"


def _stills_from_edit_list(edit_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The screens/graphics that will be drawn as AI stills and laid over the video.

    Seedance draws writing badly, so a shot that must show a screen is not asked of Seedance. The
    picture is generated by an image model, approved by the user, and shown over the footage for its
    window with the text exactly as drawn. They never overlap, so each picture gets a clear window.
    """
    stills: list[dict[str, Any]] = []
    last_end = 0.0
    for item in edit_list:
        prompt = item.get("image_prompt") or ""
        if not prompt:
            continue
        start = max(float(item["start"]), last_end)  # keep windows from overlapping
        end = float(item["end"])
        if end - start < 1.0:
            continue
        last_end = end
        stills.append(
            {
                "id": f"still-{len(stills) + 1}",
                "scene": item["scene"],
                "label": f'{item["scene_title"]} - {item["kind"]}',
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(end - start, 2),
                "image_prompt": prompt,
            }
        )
    return stills


def _end_card_spec(plan: dict[str, Any]) -> dict[str, Any] | None:
    """What the end card should say and when, taken from the script's closing scene.

    The first on-screen line is the headline, the last is the button, and any lines between are
    sub-lines. The text is the script's own, character for character.
    """
    cards = [e for e in plan["edit_list"] if e["kind"] == "end card"]
    if not cards:
        return None
    card = cards[-1]
    lines = plan["scenes"][card["scene"] - 1]["on_screen_text"]
    headline, button, subs = "", "", []
    if len(lines) == 1:
        headline = lines[0]
    elif len(lines) == 2:
        headline, button = lines
    elif len(lines) >= 3:
        headline, button, subs = lines[0], lines[-1], lines[1:-1][:3]
    hold = round(min(max(card["end"] - card["start"], 2.0), 6.0), 2)
    return {
        "headline": headline,
        "sublines": subs,
        "button_text": button,
        "start_seconds": card["start"],
        "hold_seconds": hold,
        "note": card["note"],
    }


_STATED_TOTAL = re.compile(
    r"(?i)\b(\d{1,3})[\s-]*sec(?:ond)?s?\s+(?:ad|video|film|spot|commercial|reel|clip|promo)\b"
    r"|\b(?:about|around|approx\w*|total|length|runtime|duration)\W{0,3}(\d{1,3})\s*(?:sec(?:ond)?s?|s)\b"
)


def _stated_total_seconds(script_text: str) -> int | None:
    """The overall length the script itself states ("a 20 second ad", "about 30 seconds"), if any."""
    match = _STATED_TOTAL.search(script_text or "")
    if not match:
        return None
    value = int(match.group(1) or match.group(2))
    return value if 3 <= value <= 600 else None


def build_script_plan(raw: dict[str, Any], *, clip_cap: int, script_text: str = "", sanitize: bool = False) -> dict[str, Any]:
    """Validate the planner JSON, read the script's voice, and compile the canonical prompt."""
    plan = normalize_plan(raw, clip_cap=clip_cap, script_text=script_text, sanitize=sanitize)
    voice = detect_voice(script_text)
    model_gender, speakers = _voice_from_model(raw.get("voice"))
    if not voice["gender"] and model_gender and not voice["warnings"]:
        voice = _voice_result(model_gender, voice["warnings"])  # the planner caught a phrasing my patterns missed
    plan["warnings"].extend(voice.pop("warnings"))
    on_camera = any(s["speech"] == "on_camera" for s in plan["scenes"])
    style = "natural delivery" if on_camera else "natural off-camera narration"
    voice["prompt_line"] = f'{voice["base_line"]}, {style} at a steady pace.'
    if speakers > 1:
        plan["warnings"].append(
            f"The script has {speakers} speaking voices. Creative Studio locks one voice for the whole film, so every "
            "line may be spoken by the same voice. Consider making each speaker a separate film, or recording the dialogue yourself."
        )
    stated = _stated_total_seconds(script_text)
    if stated and abs(plan["total_seconds"] - stated) >= 3:
        plan["warnings"].append(
            f"Your script says {stated} seconds but the plan runs {plan['total_seconds']}s. Adjust scene lengths if the total matters."
        )
    plan["voice"] = voice
    plan["repetition"] = _repetition(plan["scenes"])
    if plan["repetition"]:
        rep = plan["repetition"]
        plan["warnings"].append(
            f'"{rep["word"]}" appears in {rep["count"]} of {rep["total"]} shots, so the film may feel repetitive. '
            "Edit the shots in the prompt to show more people, places and cutaways."
        )
    plan["end_card"] = _end_card_spec(plan)
    # Default: no ON-SCREEN TEXT blocks, because the pipeline would burn them into the video.
    plan["canonical_prompt"] = compile_canonical_prompt(plan, voice)
    plan["canonical_prompt_with_text"] = compile_canonical_prompt(plan, voice, include_on_screen_text=True)
    return plan


# ── calling the model ───────────────────────────────────────────────────────


async def plan_script(
    *,
    script_text: str,
    model_slug: str,
    clip_cap: int,
    aspect: str = "9/16",
    brand_name: str = "",
    product_name: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Ask the LLM to plan the script, then validate and compile the answer."""
    text = (script_text or "").strip()
    if not text:
        raise ValueError("Add a script first.")
    if len(text) > MAX_SCRIPT_CHARS:
        raise ValueError(
            f"This script is too long ({len(text):,} characters; the limit is {MAX_SCRIPT_CHARS:,}). Split it into sections."
        )
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("The prompt model is not configured (OpenRouter key missing).")

    from app.services.image_prompt_service import _get_openrouter_client

    context = [
        f"Clip limit: {clip_cap} seconds per Seedance clip (minimum {MIN_SCENE_SECONDS}).",
        f"Aspect ratio: {aspect}",
        f"Brand: {brand_name or '-'}",
        f"Product: {product_name or '-'}",
    ]
    if notes.strip():
        context.append(f"Producer notes: {notes.strip()[:1500]}")
    user_payload = "CONTEXT:\n" + "\n".join(f"- {c}" for c in context) + f"\n\nSCRIPT:\n{text}\n\nRespond with the JSON object now."

    def _call(extra: str = "") -> str:
        client = _get_openrouter_client()
        completion = client.chat.completions.create(
            model=model_slug,
            temperature=0.5,  # a little freer: the shot lists should be inventive, not generic
            max_tokens=9000,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_payload + extra},
            ],
        )
        return (completion.choices[0].message.content or "").strip()

    def _badness(candidate: dict[str, Any]) -> tuple[int, float]:
        """Lower is better: first the shots that would make Seedance draw gibberish, then repetition."""
        rep = candidate.get("repetition")
        return len(candidate.get("risky_shots") or []), (rep["count"] / rep["total"] if rep else 0.0)

    def _feedback(candidate: dict[str, Any]) -> str:
        parts: list[str] = []
        risky = candidate.get("risky_shots") or []
        if risky:
            listed = "; ".join(f'scene "{r["scene"]}" shot {r["shot"]} ({", ".join(r["words"])})' for r in risky[:12])
            parts.append(
                "these shots mention things Seedance draws as garbled gibberish: " + listed + ". Rewrite exactly those "
                "shots so nothing in them has writing on it: show hands, faces, reactions, coins, parcels, a street, a "
                "shop window or a handshake instead, and never say a screen, page, notebook or sign is the subject"
            )
        rep = candidate.get("repetition")
        if rep:
            parts.append(
                f'"{rep["word"]}" appears in {rep["count"]} of {rep["total"]} shots and the plan kept to the same people '
                "and setting. Rewrite ALL the shots with real variety: at least half of every scene's shots must be "
                "cutaways (customers, products, parcels, streets, hands, objects, places) that illustrate the words "
                f'being spoken, use different people and places across scenes, and do not use "{rep["word"]}" in more '
                "than a third of the shots"
            )
        return (
            "\n\nREVISION REQUEST: your previous plan has a problem: "
            + ". Also, ".join(parts)
            + ". Keep every other field and all timings the same. Respond with the full JSON object."
        )

    raw = ""
    for attempt in (1, 2):  # one retry if the answer is not usable JSON
        try:
            raw = await asyncio.to_thread(_call)
        except Exception as exc:
            logger.exception("Script planner LLM call failed (attempt %s): %s", attempt, exc)
            if attempt == 2:
                raise ValueError("The prompt model could not be reached. Try again in a moment.") from exc
            continue
        parsed = _extract_json(raw)
        if parsed.get("scenes"):
            chosen = parsed
            plan = build_script_plan(parsed, clip_cap=clip_cap, script_text=text)
            if plan.get("repetition") or plan.get("risky_shots"):
                # One rewrite with specific feedback (known Seedance mistakes, or the same picture again and again).
                try:
                    parsed2 = _extract_json(await asyncio.to_thread(_call, _feedback(plan)))
                    if parsed2.get("scenes"):
                        second = build_script_plan(parsed2, clip_cap=clip_cap, script_text=text)
                        if _badness(second) < _badness(plan):
                            plan, chosen = second, parsed2
                except Exception:  # noqa: BLE001 - the first plan is still good enough to use
                    logger.exception("Script planner rewrite failed; keeping the first plan")
            if plan.get("risky_shots"):
                # Whatever the model still got wrong is fixed here, so the prompt is right without the user
                # having to reword anything.
                plan = build_script_plan(chosen, clip_cap=clip_cap, script_text=text, sanitize=True)
            return plan
        logger.warning("Script planner returned unusable output (attempt %s): %.200s", attempt, raw)
    raise ValueError("The planner's answer could not be read. Try again, or split the script into sections.")
