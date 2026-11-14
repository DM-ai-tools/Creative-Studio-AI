"""Pronunciation control for synthetic narration.

The speech model reads the exact words it is given, so a word it handles badly
("audit" as "aaadat", "Radius" as "Radio") is mispronounced in every video even
though the script is spelled correctly. The fix is to give the speech model a
phonetic respelling of those words while captions and the stored script keep the
original spelling.
"""

from __future__ import annotations

import re

# Words and brand names the speech model is known to get wrong. Respellings are
# written the way an Australian speaker says them, in plain letters without
# hyphens so the model does not insert pauses between syllables.
DEFAULT_LEXICON: dict[str, str] = {
    "Traffic Radius": "Traffic Raydeeus",
    "Radius": "Raydeeus",
    "audit": "awdit",
    "audits": "awdits",
    "audited": "awdited",
    "auditing": "awditing",
}

# A script can carry its own entries, one per line, for example:
#   PRONUNCIATION: Vanity Chic = Vanity Sheek
_DIRECTIVE = re.compile(
    r"(?im)^[ \t]*(?:pronunciation|pronounce)[ \t]*:[ \t]*(.+?)[ \t]*(?:=|->|→)[ \t]*(.+?)[ \t]*$"
)


def lexicon_from_brief(brief: str | None) -> dict[str, str]:
    """Default entries plus any PRONUNCIATION: lines written in the brief."""
    lexicon = dict(DEFAULT_LEXICON)
    for match in _DIRECTIVE.finditer(brief or ""):
        word, spoken = match.group(1).strip().strip("\"'"), match.group(2).strip().strip("\"'")
        if word and spoken:
            lexicon[word] = spoken
    return lexicon


def respell_for_speech(text: str, lexicon: dict[str, str]) -> tuple[str, dict[str, str]]:
    """Return the text with lexicon words respelled, and the entries that were used."""
    if not text or not lexicon:
        return text, {}
    used: dict[str, str] = {}
    spoken = text
    # Longest first so "Traffic Radius" wins over "Radius".
    for word in sorted(lexicon, key=len, reverse=True):
        pattern = re.compile(rf"(?<![\w-]){re.escape(word)}(?![\w-])", re.IGNORECASE)

        def _swap(match: re.Match[str], word: str = word) -> str:
            used[word] = lexicon[word]
            replacement = lexicon[word]
            # Keep a leading capital when the original word was capitalised.
            return replacement[:1].upper() + replacement[1:] if match.group(0)[:1].isupper() else replacement

        spoken = pattern.sub(_swap, spoken)
    return spoken, used


def pronunciation_instruction(used: dict[str, str]) -> str:
    """Tell the speech model how the respelled words should sound."""
    if not used:
        return ""
    pairs = "; ".join(f'"{spoken}" is the written form of "{word}"' for word, spoken in used.items())
    return (
        "Pronounce every word exactly as spelled, sounding it out naturally as a single smooth word "
        f"with no pauses between its parts. Pronunciation notes: {pairs}. "
    )


# --- Native presenter speech -------------------------------------------------
# Seedance speaks the dialogue itself, so the respelling has to be written into the
# prompt it receives. Only the spoken lines are changed: respelling a brand name in a
# visual direction could make the model draw the misspelled word on screen.

_SPOKEN_LABEL = re.compile(
    r"(?i)^(?P<lead>[ \t]*(?:[-*][ \t]*)?"
    r"(?:dialogue|voice[ -]?over|vo|narration|narrator|speak exactly|spoken line|says)"
    r"(?:[ \t]*(?:,|\()[^:\n]*?)?[ \t]*:[ \t]*)(?P<rest>.*)$"
)
_OTHER_LABEL = re.compile(
    r"(?i)^[ \t]*(?:[-*][ \t]*)?(?:visual|scene|camera|sound|music|look|character|screens|movement|light|"
    r"text overlay|on-screen text|audio|style|note)\b[^\n]*?:"
)


def respell_spoken_lines(prompt: str, lexicon: dict[str, str] | None = None) -> str:
    """Respell lexicon words in dialogue/voiceover lines of a Seedance prompt, nothing else."""
    if not prompt:
        return prompt
    lexicon = lexicon if lexicon is not None else lexicon_from_brief(prompt)
    out: list[str] = []
    in_spoken_block = False
    for line in prompt.split("\n"):
        match = _SPOKEN_LABEL.match(line)
        if match:
            rest = match.group("rest")
            if rest.strip():
                line = match.group("lead") + respell_for_speech(rest, lexicon)[0]
                in_spoken_block = False
            else:
                in_spoken_block = True  # the spoken text starts on the next line
        elif in_spoken_block:
            if not line.strip() or _OTHER_LABEL.match(line):
                in_spoken_block = False
            else:
                line = respell_for_speech(line, lexicon)[0]
        out.append(line)
    return "\n".join(out)
