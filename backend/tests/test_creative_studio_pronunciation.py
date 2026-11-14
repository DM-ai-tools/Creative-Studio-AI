"""Narration respells words the speech model mispronounces; captions keep the original spelling."""

from app.services.creative_studio_pronunciation import (
    lexicon_from_brief,
    pronunciation_instruction,
    respell_for_speech,
)


def test_brand_and_problem_words_are_respelled():
    lexicon = lexicon_from_brief("")
    spoken, used = respell_for_speech("Book your free audit with Traffic Radius today.", lexicon)
    assert spoken == "Book your free awdit with Traffic Raydeeus today."
    assert set(used) == {"audit", "Traffic Radius"}


def test_longest_entry_wins_and_capitals_are_kept():
    lexicon = lexicon_from_brief("")
    spoken, _ = respell_for_speech("Audit first. Then Radius.", lexicon)
    assert spoken == "Awdit first. Then Raydeeus."


def test_whole_words_only():
    spoken, used = respell_for_speech("The auditorium and radius-x stay as written.", lexicon_from_brief(""))
    assert spoken == "The auditorium and radius-x stay as written."
    assert used == {}


def test_script_can_add_its_own_entries():
    lexicon = lexicon_from_brief("PRONUNCIATION: Vanity Chic = Vanity Sheek\nSCENE 1 — 0:00–0:05")
    spoken, used = respell_for_speech("Vanity Chic grew fast.", lexicon)
    assert spoken == "Vanity Sheek grew fast." and used == {"Vanity Chic": "Vanity Sheek"}


def test_text_without_listed_words_is_untouched_and_gives_no_instruction():
    spoken, used = respell_for_speech("Your ads aren't failing.", lexicon_from_brief(""))
    assert spoken == "Your ads aren't failing." and used == {}
    assert pronunciation_instruction(used) == ""


def test_instruction_names_each_respelling():
    note = pronunciation_instruction({"audit": "awdit"})
    assert '"awdit"' in note and '"audit"' in note


# --- native presenter speech: only spoken lines are respelled -------------------

from app.services.creative_studio_pronunciation import respell_spoken_lines

NATIVE_PROMPT = """LOOK: Traffic Radius office, glass walls.
SCENE 3 — 0:09–0:13 — PRESENTER
VISUAL: She stands beside a wall that reads Traffic Radius and gestures.
DIALOGUE:
"In our free 30-minute Google Ads audit at Traffic Radius."
"Book your audit today."

SCENE 4 — 0:13–0:17 — PRESENTER
SPEAK EXACTLY: "Book your free audit with Traffic Radius."
Voiceover, 0–5 seconds: "We run a full audit."
NARRATION CUES FOR VISUAL ALIGNMENT ONLY — DO NOT SPEAK THEM:
local 0-5s: audit at Traffic Radius
"""


def test_native_dialogue_in_every_script_format_is_respelled():
    out = respell_spoken_lines(NATIVE_PROMPT)
    assert '"In our free 30-minute Google Ads awdit at Traffic Raydeeus."' in out
    assert '"Book your awdit today."' in out
    assert 'SPEAK EXACTLY: "Book your free awdit with Traffic Raydeeus."' in out
    assert 'Voiceover, 0–5 seconds: "We run a full awdit."' in out


def test_visual_directions_and_cues_keep_the_real_spelling():
    out = respell_spoken_lines(NATIVE_PROMPT)
    assert "LOOK: Traffic Radius office" in out
    assert "reads Traffic Radius and gestures" in out
    assert "local 0-5s: audit at Traffic Radius" in out


def test_prompt_without_dialogue_is_unchanged():
    text = "VISUAL: A calm audit of a Radius sign.\nSOUND: music only"
    assert respell_spoken_lines(text) == text


def test_seedance_request_is_respelled_only_when_it_speaks():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.media import byteplus_seedance_client as client_module

    sent: list[dict] = []

    async def fake_request(_client, _method, _url, **kwargs):
        sent.append(kwargs["json"])
        response = MagicMock(status_code=200, content=b"{}", text="{}")
        response.json.return_value = {"id": "task-1"}
        return response

    async def run(audio: bool):
        with patch.object(client_module, "async_request_with_retry", new=AsyncMock(side_effect=fake_request)), \
             patch.object(client_module, "ark_headers", return_value={}), \
             patch.object(client_module, "ark_base_url", return_value="https://ark.test"):
            await client_module.create_video_task(
                MagicMock(), prompt=NATIVE_PROMPT, model="ark-seedance-2-5", duration=8, generate_audio=audio
            )

    asyncio.run(run(True))
    asyncio.run(run(False))
    spoken, silent = sent[0]["content"][0]["text"], sent[1]["content"][0]["text"]
    assert "Traffic Raydeeus" in spoken and "awdit" in spoken
    assert silent == NATIVE_PROMPT.strip()
