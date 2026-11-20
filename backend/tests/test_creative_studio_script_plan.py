import asyncio
import io
import json
import re

import pytest
from docx import Document

from app.services import creative_studio_script_plan as sp
from app.services.creative_studio_timeline import explicit_shot_windows
from app.services.creative_studio_video_finishing import (
    extract_overlay_events,
    extract_voiceover_events,
)


def _scene(**over):
    base = {
        "title": "The hook",
        "duration_seconds": 8,
        "duration_source": "script",
        "voiceover": "Running an online store? How much of your budget is going to the wrong people?",
        "visual_direction": "A store owner at a laptop in a bright modern office, slow pull-back, soft daylight.",
        "on_screen_text": ["PAYING FOR CLICKS, NOT CUSTOMERS?"],
        "edit_inserts": [],
        "reason": "live action plus a screen insert",
    }
    base.update(over)
    return base


# ── reading the script ──────────────────────────────────────────────────────


def _docx_bytes() -> bytes:
    doc = Document()
    doc.add_paragraph("Scene 1 (0:00-0:06): woman opens laptop")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Scene 2 (6s)"
    table.cell(0, 1).text = "Show app dashboard screen recording"
    table.cell(1, 0).text = "Scene 3 (5s)"
    table.cell(1, 1).text = "Logo end card"
    doc.add_paragraph("End of script")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_docx_reads_paragraphs_and_tables_in_order():
    lines = sp.extract_script_text(_docx_bytes(), "script.docx").splitlines()
    assert lines[0].startswith("Scene 1")
    assert lines[1] == "Scene 2 (6s) | Show app dashboard screen recording"
    assert lines[2] == "Scene 3 (5s) | Logo end card"
    assert lines[-1] == "End of script"


def test_text_files_and_bad_types():
    assert sp.extract_script_text(b"hello", "a.txt") == "hello"
    with pytest.raises(ValueError, match=r"\.docx"):
        sp.extract_script_text(b"x", "a.doc")
    with pytest.raises(ValueError):
        sp.extract_script_text(b"x", "a.pdf")
    with pytest.raises(ValueError, match="empty"):
        sp.extract_script_text(b"   ", "a.txt")
    with pytest.raises(ValueError, match="Could not read"):
        sp.extract_script_text(b"not a zip", "a.docx")


# ── the voice the script asks for ───────────────────────────────────────────


def test_voice_is_read_from_the_script():
    voice = sp.detect_voice("Voice: Australian English female voice, warm and clear.\nSCENE 1 ...")
    assert (voice["gender"], voice["accent"], voice["source"]) == ("female", "Australian English", "script")
    assert "Australian English female voice" in voice["prompt_line"]
    male = sp.detect_voice("Narrator: Australian male voice, 145 words per minute.")
    assert (male["gender"], male["accent"]) == ("male", "Australian English")
    assert "male voice" in male["prompt_line"] and "female" not in male["prompt_line"]


def test_visual_directions_do_not_set_the_voice():
    script = (
        "AI visual direction:\nA realistic close-up of an Australian e-commerce owner on a laptop.\n"
        'Exact voiceover:\n"Running an online store? A woman and a man will never buy."'
    )
    voice = sp.detect_voice(script)
    # no gender chosen by the script; the accent is still always Australian English
    assert voice["gender"] == "" and voice["source"] == "default"
    assert voice["base_line"] == "Australian English voice"


def test_conflicting_voice_hints_lock_no_gender_and_warn():
    voice = sp.detect_voice("Voice: female voice.\nNarrator: male voice.")
    assert voice["gender"] == "" and voice["warnings"]
    assert voice["accent"] == "Australian English"


def test_the_accent_is_always_australian_english_whatever_the_script_says():
    for script in (
        "Voice: American English female voice.",
        "Narrator: British male voice, London accent.",
        "Voz: voz femenina, español de México.",
        "",
    ):
        voice = sp.detect_voice(script)
        assert voice["accent"] == "Australian English", script
        assert voice["base_line"].startswith("Australian English"), script
        assert "american" not in voice["prompt_line"].lower() and "british" not in voice["prompt_line"].lower()
    # the script may still choose male or female
    assert sp.detect_voice("Voice: American English female voice.")["gender"] == "female"
    assert sp.detect_voice("Narrator: British male voice.")["gender"] == "male"


# ── validation ──────────────────────────────────────────────────────────────


def test_timeline_has_no_gaps_and_edit_list_uses_absolute_times():
    plan = sp.normalize_plan(
        {
            "scenes": [
                _scene(duration_seconds=8, edit_inserts=[{"starts_at_seconds": 4, "duration_seconds": 4, "kind": "screen", "note": "report mock-up"}]),
                _scene(title="Close", duration_seconds=9, edit_inserts=[{"starts_at_seconds": 3, "duration_seconds": 6, "kind": "end card", "note": "logo and CTA"}]),
            ]
        },
        clip_cap=30,
    )
    assert [(s["start"], s["end"]) for s in plan["scenes"]] == [(0, 8), (8, 17)]
    assert plan["total_seconds"] == 17
    planned = [e for e in plan["edit_list"] if e["kind"] != "text"]  # text entries are checked separately
    assert [(e["scene"], e["start"], e["end"], e["kind"]) for e in planned] == [
        (1, 4.0, 8.0, "screen"),
        (2, 11.0, 17.0, "end card"),
    ]
    assert [e["start"] for e in plan["edit_list"]] == sorted(e["start"] for e in plan["edit_list"])


def test_estimated_durations_follow_the_voiceover_not_the_models_guess():
    line = " ".join(["word"] * 25)  # 25 words -> ceil(10 + 0.5) = 11s
    plan = sp.normalize_plan(
        {"scenes": [_scene(duration_source="estimated", duration_seconds=20, voiceover=line)]},
        clip_cap=30,
    )
    assert plan["scenes"][0]["duration_seconds"] == 11
    # but durations written in the script are kept
    plan = sp.normalize_plan(
        {"scenes": [_scene(duration_source="script", duration_seconds=20, voiceover=line)]},
        clip_cap=30,
    )
    assert plan["scenes"][0]["duration_seconds"] == 20


def test_short_scene_lengthened_long_scene_flagged_inserts_clamped():
    plan = sp.normalize_plan(
        {
            "scenes": [
                _scene(duration_seconds=2, voiceover="", edit_inserts=[{"starts_at_seconds": 99, "duration_seconds": 99, "note": "x"}]),
                _scene(title="Long", duration_seconds=40),
            ]
        },
        clip_cap=30,
    )
    assert plan["scenes"][0]["duration_seconds"] == 4
    assert any("at least 4s" in w for w in plan["warnings"])
    assert any("longer than one Seedance clip" in w for w in plan["warnings"])
    insert = plan["edit_list"][0]
    assert plan["scenes"][0]["start"] <= insert["start"] < insert["end"] <= plan["scenes"][0]["end"]


def test_missing_footage_direction_gets_a_placeholder_never_blank():
    plan = sp.normalize_plan({"scenes": [_scene(visual_direction="  ")]}, clip_cap=30)
    assert plan["scenes"][0]["visual_direction"]
    assert any("neutral placeholder" in w for w in plan["warnings"])


def test_junk_rows_and_empty_plans():
    plan = sp.normalize_plan({"scenes": ["junk", _scene(duration_seconds=None, duration_source="script")]}, clip_cap=30)
    assert len(plan["scenes"]) == 1 and plan["scenes"][0]["duration_seconds"] == 4
    for bad in ({}, {"scenes": []}, {"scenes": ["x"]}):
        with pytest.raises(ValueError):
            sp.normalize_plan(bad, clip_cap=30)


def test_warns_only_when_a_spoken_line_cannot_fit_its_scene():
    line = " ".join(["word"] * 25)  # ~10s of speech
    tight = sp.normalize_plan({"scenes": [_scene(duration_seconds=6, voiceover=line)]}, clip_cap=30)
    assert any("needs about 10s but the scene is 6s" in w for w in tight["warnings"])
    # a scene that is longer than its line is normal (music, pauses): no warning
    roomy = sp.normalize_plan(
        {"scenes": [_scene(duration_seconds=20, voiceover=line), _scene(duration_seconds=20, voiceover="")]},
        clip_cap=30,
    )
    assert not any("spoken line" in w for w in roomy["warnings"])


def test_insert_keeps_its_planned_length_and_moves_earlier_instead_of_shrinking():
    plan = sp.normalize_plan(
        {"scenes": [_scene(duration_seconds=9, edit_inserts=[{"starts_at_seconds": 8, "duration_seconds": 3, "kind": "text card", "note": "x"}])]},
        clip_cap=30,
    )
    insert = [e for e in plan["edit_list"] if e["kind"] == "text card"][0]
    assert (insert["start"], insert["end"]) == (6.0, 9.0)  # still 3s, moved earlier to fit


def test_on_camera_speaker_keeps_the_presenter_and_card_goes_over_the_last_seconds():
    row = _scene(
        title="Offer",
        speech="on_camera",
        duration_source="estimated",
        voiceover="Use code GLOW20 for twenty percent off at glowserum dot com.",
        visual_direction="The presenter looks into camera, smiling, in a bright bathroom.",
        closing_card={"line": "Use code GLOW20 for twenty percent off at glowserum dot com.", "note": "logo and code"},
        edit_inserts=[],
        on_screen_text=[],
    )
    plan = sp.normalize_plan({"scenes": [row]}, clip_cap=30)
    assert len(plan["scenes"]) == 1  # not split, presenter stays on screen
    scene = plan["scenes"][0]
    assert "presenter" in scene["visual_direction"] and scene["visual_direction"] != sp.EMPTY_BACKGROUND
    assert scene["speech"] == "on_camera"
    card = [e for e in plan["edit_list"] if e["kind"] == "end card"][0]
    assert card["end"] == scene["end"] and card["end"] - card["start"] == min(4, scene["duration_seconds"])


def test_silent_end_card_scene_gets_an_empty_background_even_without_a_closing_card_field():
    row = _scene(
        title="End Card",
        voiceover="",
        speech="none",
        duration_seconds=4,
        visual_direction="Black end card with the Northstar logo and the line Time well spent.",
        on_screen_text=[],
        edit_inserts=[{"starts_at_seconds": 0, "duration_seconds": 4, "kind": "end card", "note": "logo + tagline"}],
    )
    plan = sp.normalize_plan({"scenes": [row]}, clip_cap=30)
    assert plan["scenes"][0]["visual_direction"] == sp.EMPTY_BACKGROUND
    assert not any("logo" in w for w in plan["warnings"])


def test_voice_line_matches_how_the_script_speaks():
    narr = sp.build_script_plan({"scenes": [_scene(speech="voiceover")]}, clip_cap=30, script_text="Voice: Australian English female voice.")
    assert "off-camera narration" in narr["voice"]["prompt_line"]
    ugc = sp.build_script_plan({"scenes": [_scene(speech="on_camera")]}, clip_cap=30, script_text="Voice: female voice.")
    assert "off-camera" not in ugc["voice"]["prompt_line"] and "Australian English female voice" in ugc["voice"]["prompt_line"]
    assert "off-camera" not in ugc["canonical_prompt"]


def test_the_planners_reading_of_gender_is_a_fallback_and_never_trusted_blindly():
    # a phrasing my patterns miss, but the planner caught
    plan = sp.build_script_plan({"voice": {"gender": "male", "speakers": 1}, "scenes": [_scene()]}, clip_cap=30, script_text="A deep gentleman reads it.")
    assert (plan["voice"]["gender"], plan["voice"]["accent"], plan["voice"]["source"]) == ("male", "Australian English", "script")
    assert "Australian English male voice" in plan["canonical_prompt"]
    # an accent the planner returns is ignored: the film is always Australian English
    odd = sp.build_script_plan({"voice": {"gender": "female", "accent": "Mexican Spanish"}, "scenes": [_scene()]}, clip_cap=30, script_text="")
    assert odd["voice"]["accent"] == "Australian English" and "Mexican" not in odd["canonical_prompt"]
    # junk values are ignored
    junk = sp.build_script_plan({"voice": {"gender": "robot", "speakers": "many"}, "scenes": [_scene()]}, clip_cap=30, script_text="")
    assert junk["voice"]["gender"] == "" and junk["voice"]["base_line"] == "Australian English voice"
    # the existing voice lock only reads English phrases like "female voice"; it finds this one
    assert re.search(r"\b(?:female voice|female presenter|woman presenter)\b", odd["canonical_prompt"].lower())


def test_several_speakers_are_flagged_because_one_voice_is_locked_per_film():
    plan = sp.build_script_plan({"voice": {"speakers": 2}, "scenes": [_scene()]}, clip_cap=30, script_text="x")
    assert any("2 speaking voices" in w and "one voice" in w for w in plan["warnings"])


def test_stated_total_length_is_compared_with_the_plan():
    assert sp._stated_total_seconds("Make a 20 second ad for a cafe") == 20
    assert sp._stated_total_seconds("UGC TESTIMONIAL (about 30 seconds)") == 30
    assert sp._stated_total_seconds("FILM — 39 SECOND FILM") == 39
    assert sp._stated_total_seconds("SCENE 1 | 0-9 SECONDS") is None  # a scene window is not a total
    close = sp.build_script_plan({"scenes": [_scene(duration_seconds=18, voiceover="")]}, clip_cap=30, script_text="a 20 second ad")
    assert not any("Your script says" in w for w in close["warnings"])  # 2s off is fine
    off = sp.build_script_plan({"scenes": [_scene(duration_seconds=17, voiceover="")]}, clip_cap=30, script_text="a 20 second ad")
    assert any("says 20 seconds but the plan runs 17s" in w for w in off["warnings"])  # 3s or more is flagged
    far = sp.build_script_plan({"scenes": [_scene(duration_seconds=12, voiceover="")]}, clip_cap=30, script_text="a 20 second ad")
    assert any("says 20 seconds but the plan runs 12s" in w for w in far["warnings"])


# ── the prompt handed to the existing pipeline ──────────────────────────────

_SCRIPT = "Voice: Australian English female voice.\nScene 1 (8s) ... Scene 2 (7s) ... Scene 3 (9s) ..."


def _built():
    raw = {
        "title": "Traffic Radius - Paying for shoppers who never buy",
        "global_style": "Cool navy and teal grade, soft office daylight.",
        "scenes": [
            _scene(),
            _scene(
                title="Explain the problem",
                duration_seconds=7,
                voiceover='Your campaigns might get "plenty" of clicks, but irrelevant searches eat your budget.',
                on_screen_text=["Wrong Searches. Wasted Spend."],
            ),
            _scene(title="Offer and CTA", duration_seconds=9, voiceover="Book your free audit.", on_screen_text=[]),
        ],
    }
    return sp.build_script_plan(raw, clip_cap=30, script_text=_SCRIPT)


def test_existing_parsers_read_the_canonical_prompt_like_a_pasted_one():
    plan = _built()
    prompt = plan["canonical_prompt"]
    windows = explicit_shot_windows(prompt)
    assert windows == [(0.0, 8.0), (8.0, 15.0), (15.0, 24.0)]
    events = extract_voiceover_events(prompt, duration_seconds=24)
    assert [(a, b) for a, b, _ in events] == windows
    assert events[1][2] == "Your campaigns might get 'plenty' of clicks, but irrelevant searches eat your budget."
    # the optional with-text version is read by the on-screen text reader as intended
    with_text = plan["canonical_prompt_with_text"]
    overlays = extract_overlay_events(with_text)
    assert (0.0, 8.0, "PAYING FOR CLICKS, NOT CUSTOMERS?") in overlays
    assert (8.0, 15.0, "Wrong Searches. Wasted Spend.") in overlays
    assert explicit_shot_windows(with_text) == windows
    assert [(a, b) for a, b, _ in extract_voiceover_events(with_text, duration_seconds=24)] == windows


def test_default_prompt_leaves_text_to_the_editor_so_nothing_is_burned_in():
    plan = _built()
    prompt = plan["canonical_prompt"]
    assert "ON-SCREEN TEXT" not in prompt
    assert extract_overlay_events(prompt) == []  # the pipeline finds no text to burn in
    assert "PAYING FOR CLICKS" not in prompt
    # voice and timing are untouched by leaving the text out
    assert explicit_shot_windows(prompt) == [(0.0, 8.0), (8.0, 15.0), (15.0, 24.0)]
    assert len(extract_voiceover_events(prompt, duration_seconds=24)) == 3
    # the editor still gets the exact lines and when to place them
    texts = [e for e in plan["edit_list"] if e["kind"] == "text"]
    assert [(e["start"], e["end"]) for e in texts] == [(0.0, 8.0), (8.0, 15.0)]
    assert "PAYING FOR CLICKS, NOT CUSTOMERS?" in texts[0]["note"]


def test_text_entry_not_duplicated_when_planner_already_listed_a_text_card():
    raw = {
        "scenes": [
            _scene(edit_inserts=[{"starts_at_seconds": 2, "duration_seconds": 4, "kind": "text card", "note": "lower third, white bold"}])
        ]
    }
    plan = sp.normalize_plan(raw, clip_cap=30)
    assert [e["kind"] for e in plan["edit_list"]] == ["text card"]


_FLAGGED_BY_THE_USER = [
    "Close-up of a notepad with scribbled figures and a circled dollar sign.",
    "Overhead of a hand scrolling a spreadsheet beside the laptop.",
    "A highlighter on a section labelled 'Search Intent' in a stack of printouts.",
    "A magnifying glass over the words 'Negative Keywords' and 'Campaign Spend', then pulling away.",
    "The owner taps a phone screen showing a spending counter, a dashboard glowing behind.",
    "A van with lettering on its side beside a shop sign with the logo.",
]


def test_known_seedance_mistakes_are_rewritten_by_the_code_so_the_user_never_has_to():
    for text in _FLAGGED_BY_THE_USER:
        assert sp._risky_footage_words(text), text  # these really are the known problems
        fixed = sp.sanitize_footage_text(text)
        assert sp._risky_footage_words(fixed) == [], (text, fixed)
        assert fixed and not fixed.startswith(" ") and "  " not in fixed and " ," not in fixed
        assert sp.sanitize_footage_text(fixed) == fixed  # safe to run twice
    assert "folder" in sp.sanitize_footage_text(_FLAGGED_BY_THE_USER[0])
    assert "Search Intent" not in sp.sanitize_footage_text(_FLAGGED_BY_THE_USER[2])
    assert "Negative Keywords" not in sp.sanitize_footage_text(_FLAGGED_BY_THE_USER[3])


def test_cleanup_reads_naturally_and_does_not_mangle_the_sentence():
    assert sp.sanitize_footage_text("A marker circling a pie chart on the wall.") == "A marker circling a coloured shapes on the wall."
    assert "pie papers" not in sp.sanitize_footage_text("circling a pie chart")
    # protected phrases keep their exact spacing: no stray space is added before them, no words are fused after
    assert sp.sanitize_footage_text("A wall (no writing visible), then a pan.") == "A wall (no writing visible), then a pan."
    assert sp.sanitize_footage_text("A wall with a notebook (no writing visible), then a pan.") == "A wall with a folder (no writing visible), then a pan."
    assert sp.sanitize_footage_text("No readable text and a notepad on the desk.") == "No readable text and a folder on the desk."
    assert sp.sanitize_footage_text("A desk, never a whiteboard, with a logo on it.") == "A desk, never a whiteboard, with a plain surface on it."
    assert sp.sanitize_footage_text("A van with a logo, then a street.") == "A van with a plain surface, then a street."


def test_phrases_the_model_wrote_as_negations_are_left_exactly_as_written():
    text = "The laptop screen glows softly, out of focus; no readable text or logos anywhere, and a notepad on the desk."
    fixed = sp.sanitize_footage_text(text)
    assert "no readable text or logos anywhere" in fixed  # the safe instruction is untouched
    assert "notepad" not in fixed and "folder" in fixed  # the real problem beside it is fixed
    assert sp.sanitize_footage_text(sp.EMPTY_BACKGROUND) == sp.EMPTY_BACKGROUND
    assert sp.sanitize_footage_text(sp.LEAD_IN_CONTINUATION) == sp.LEAD_IN_CONTINUATION


def test_sanitized_plans_carry_no_warnings_about_those_words_and_plain_plans_still_record_them():
    scenes = [_scene(duration_seconds=6, shots=_shots((3, _FLAGGED_BY_THE_USER[0]), (3, _FLAGGED_BY_THE_USER[1])))]
    plain = sp.normalize_plan({"scenes": scenes}, clip_cap=30)
    assert [r["shot"] for r in plain["risky_shots"]] == [1, 2]
    assert any("garbled readable text" in w for w in plain["warnings"])
    clean = sp.normalize_plan({"scenes": scenes}, clip_cap=30, sanitize=True)
    assert clean["risky_shots"] == [] and not any("garbled" in w for w in clean["warnings"])
    assert "notepad" not in clean["scenes"][0]["visual_direction"] and "spreadsheet" not in clean["scenes"][0]["visual_direction"]
    assert [s["seconds"] for s in clean["scenes"][0]["shots"]] == [3, 3]  # timing untouched


def _raw_with_shots(descriptions):
    return json.dumps({"scenes": [_scene(duration_seconds=3 * len(descriptions), shots=_shots(*[(3, d) for d in descriptions]))]})


_SAFE_SHOTS = ["A hand drops coins one by one into a jar.", "A courier hands over a parcel at a door.", "A shopper walks past a lit window display."]


def _run_with_replies(monkeypatch, replies):
    from app.services import image_prompt_service

    client = _FakeClient(replies)
    monkeypatch.setattr(image_prompt_service, "_get_openrouter_client", lambda: client)
    monkeypatch.setattr(sp.settings, "OPENROUTER_API_KEY", "test-key", raising=False)
    plan = asyncio.run(sp.plan_script(script_text="Scene 1 ...", model_slug="m", clip_cap=30))
    return plan, client


def test_planner_asks_for_a_rewrite_naming_the_bad_shots_and_uses_the_clean_answer(monkeypatch):
    first = _raw_with_shots(_FLAGGED_BY_THE_USER[:3])
    plan, client = _run_with_replies(monkeypatch, [first, _raw_with_shots(_SAFE_SHOTS)])
    asked = client.last["messages"][1]["content"]
    assert client.calls == 2 and "REVISION REQUEST" in asked
    assert "notepad" in asked and "spreadsheet" in asked and "labelled" in asked  # it names exactly what to fix
    assert plan["risky_shots"] == [] and not any("garbled" in w for w in plan["warnings"])
    assert "coins" in plan["scenes"][0]["visual_direction"]  # the model's clean rewrite was used


def test_if_the_rewrite_still_has_the_problem_the_code_fixes_it_with_no_third_call_and_no_warning(monkeypatch):
    bad = _raw_with_shots(_FLAGGED_BY_THE_USER[:3])
    plan, client = _run_with_replies(monkeypatch, [bad, bad])
    assert client.calls == 2
    assert plan["risky_shots"] == [] and not any("garbled" in w for w in plan["warnings"])
    text = plan["scenes"][0]["visual_direction"]
    assert "notepad" not in text and "spreadsheet" not in text and "Search Intent" not in text
    # the same when the rewrite request itself fails: the first plan is cleaned and returned
    plan2, _ = _run_with_replies(monkeypatch, [bad, RuntimeError("boom")])
    assert plan2["risky_shots"] == [] and "notepad" not in plan2["scenes"][0]["visual_direction"]


def test_a_clean_plan_costs_one_call_and_is_returned_untouched(monkeypatch):
    plan, client = _run_with_replies(monkeypatch, [_raw_with_shots(_SAFE_SHOTS)])
    assert client.calls == 1 and plan["risky_shots"] == []
    assert plan["scenes"][0]["shots"][0]["description"] == _SAFE_SHOTS[0]


def test_labels_and_words_in_the_footage_are_flagged_as_readable_text():
    for text in (
        "A highlighter on a section labelled 'Search Intent' in the printouts.",
        "A magnifying glass over the words on a page.",
        "A van with lettering on its side.",
        "Close-up of a notebook with a circled dollar sign.",
        "A whiteboard with arrows drawn across it.",
        "A spreadsheet fills the screen as a hand scrolls.",
    ):
        plan = sp.normalize_plan({"scenes": [_scene(visual_direction=text)]}, clip_cap=30)
        assert any("garbled readable text" in w for w in plan["warnings"]), text
    clean = sp.normalize_plan({"scenes": [_scene(visual_direction="A hand sweeps a highlighter across a stack of paper, far out of focus.")]}, clip_cap=30)
    assert not any("garbled readable text" in w for w in clean["warnings"])


def test_end_card_held_for_a_whole_scene_is_flagged_but_a_short_one_is_not():
    long_card = _scene(
        title="Offer",
        duration_seconds=10,
        edit_inserts=[{"starts_at_seconds": 0, "duration_seconds": 10, "kind": "end card", "note": "logo and CTA"}],
    )
    plan = sp.normalize_plan({"scenes": [long_card]}, clip_cap=30)
    assert any("end card is on screen for 10s" in w for w in plan["warnings"])

    split = [
        _scene(title="Lead-in", duration_seconds=6, voiceover="You will get clear recommendations with no fees."),
        _scene(
            title="CTA",
            duration_seconds=4,
            voiceover="Book your free audit.",
            edit_inserts=[{"starts_at_seconds": 0, "duration_seconds": 4, "kind": "end card", "note": "logo and CTA"}],
        ),
    ]
    ok = sp.normalize_plan({"scenes": split}, clip_cap=30)
    assert not any("end card" in w for w in ok["warnings"])
    assert [(s["start"], s["end"]) for s in ok["scenes"]] == [(0, 6), (6, 10)]
    # voiceover stays continuous across the split for the existing parser
    prompt = sp.build_script_plan({"scenes": split}, clip_cap=30)["canonical_prompt"]
    assert [(a, b) for a, b, _ in extract_voiceover_events(prompt, duration_seconds=10)] == [(0.0, 6.0), (6.0, 10.0)]


_CTA_VOICE = (
    "You'll get clear recommendations, with no fees and no pressure to work with us. "
    "Book your free Google Ads audit with Traffic Radius."
)
_CTA_LINE = "Book your free Google Ads audit with Traffic Radius."


def _closing(**over):
    return _scene(
        title="Offer and CTA",
        duration_source="estimated",
        duration_seconds=10,
        voiceover=_CTA_VOICE,
        visual_direction="The strategist hands a printed summary across a desk and smiles.",
        on_screen_text=["FREE GOOGLE ADS AUDIT", "BOOK YOUR FREE AUDIT"],
        edit_inserts=[{"starts_at_seconds": 0, "duration_seconds": 10, "kind": "end card", "note": "logo, blue CTA button"}],
        closing_card={"line": _CTA_LINE, "note": "Logo left, blue button, green tick; use the supplied logo unchanged."},
        **over,
    )


def test_closing_scene_is_split_so_the_end_card_holds_only_over_the_call_to_action():
    plan = sp.normalize_plan({"scenes": [_closing()]}, clip_cap=30)
    lead, cta = plan["scenes"]
    # lead-in keeps the planner's real footage and its own sentence
    assert lead["visual_direction"].startswith("The strategist hands")
    assert lead["voiceover"].endswith("work with us.") and "Book your free" not in lead["voiceover"]
    assert lead["on_screen_text"] == []
    # the call to action is short and sits on an empty background written by the code
    assert cta["voiceover"] == _CTA_LINE
    assert cta["title"].endswith("call to action")
    assert cta["visual_direction"] == sp.EMPTY_BACKGROUND
    assert cta["duration_seconds"] == 4 and lead["duration_seconds"] == 6
    assert cta["on_screen_text"] == ["FREE GOOGLE ADS AUDIT", "BOOK YOUR FREE AUDIT"]
    card = [e for e in plan["edit_list"] if e["kind"] == "end card"]
    assert [(e["start"], e["end"]) for e in card] == [(cta["start"], cta["end"])]
    assert "unchanged" in card[0]["note"]
    # the voiceover is continuous and complete across the two parts
    assert (lead["end"], cta["start"]) == (lead["end"], lead["end"])
    assert f'{lead["voiceover"]} {cta["voiceover"]}' == _CTA_VOICE
    assert not any("end card is on screen" in w for w in plan["warnings"])


def test_lead_in_that_describes_the_end_card_carries_on_from_the_previous_scene_instead():
    row = _closing()
    row["visual_direction"] = "A premium end card: a laptop on the right and the Traffic Radius logo with a CTA button on the left."
    lead, cta = sp.normalize_plan({"scenes": [row]}, clip_cap=30)["scenes"]
    assert lead["visual_direction"] == sp.LEAD_IN_CONTINUATION
    assert "logo" not in lead["visual_direction"].lower()
    assert cta["visual_direction"] == sp.EMPTY_BACKGROUND
    # clean footage is left alone
    clean = _closing()
    lead, _ = sp.normalize_plan({"scenes": [clean]}, clip_cap=30)["scenes"]
    assert lead["visual_direction"].startswith("The strategist hands")


def test_closing_split_respects_script_durations_and_whole_scene_cta():
    scripted = sp.normalize_plan({"scenes": [_closing(**{})]}, clip_cap=30)  # estimated baseline
    assert scripted["total_seconds"] == 10
    row = _closing()
    row["duration_source"], row["duration_seconds"] = "script", 12
    lead, cta = sp.normalize_plan({"scenes": [row]}, clip_cap=30)["scenes"]
    assert (lead["duration_seconds"], cta["duration_seconds"]) == (8, 4)  # script total kept: 12s

    only_cta = _closing()
    only_cta["voiceover"] = _CTA_LINE
    scenes = sp.normalize_plan({"scenes": [only_cta]}, clip_cap=30)["scenes"]
    assert len(scenes) == 1 and scenes[0]["visual_direction"] == sp.EMPTY_BACKGROUND
    assert scenes[0]["voiceover"] == _CTA_LINE


def test_closing_card_line_not_at_the_end_leaves_the_scene_as_planned():
    row = _closing()
    row["closing_card"] = {"line": "Something never said", "note": "x"}
    scenes = sp.normalize_plan({"scenes": [row]}, clip_cap=30)["scenes"]
    assert len(scenes) == 1 and scenes[0]["visual_direction"].startswith("The strategist hands")


def test_split_prompt_is_read_correctly_by_the_existing_parsers():
    prompt = sp.build_script_plan({"scenes": [_scene(duration_seconds=8), _closing()]}, clip_cap=30)["canonical_prompt"]
    windows = explicit_shot_windows(prompt)
    assert windows == [(0.0, 8.0), (8.0, 14.0), (14.0, 18.0)]
    events = extract_voiceover_events(prompt, duration_seconds=18)
    assert [(a, b) for a, b, _ in events] == windows
    assert events[2][2] == _CTA_LINE


def _shots(*pairs):
    return [{"seconds": s, "description": d} for s, d in pairs]


def test_shot_list_is_fitted_to_the_scene_whole_seconds_none_under_two_and_summing_exactly():
    shots = _shots((3, "Close-up: a store owner snaps a laptop shut."), (3, "Overhead: parcels slide along a packing bench."), (3, "Wide: a shopper abandons a cart and walks out."))
    plan = sp.normalize_plan({"scenes": [_scene(duration_seconds=9, shots=shots, visual_direction="")]}, clip_cap=30)
    scene = plan["scenes"][0]
    assert [s["seconds"] for s in scene["shots"]] == [3, 3, 3]
    assert "Shot 1 (3s): Close-up" in scene["visual_direction"] and "Shot 3 (3s): Wide" in scene["visual_direction"]
    assert not any("single shot" in w or "no cuts" in w for w in plan["warnings"])
    # a different length: proportions are kept, every shot >= 2s, total exact
    for duration in (7, 8, 10, 12, 13):
        planned = sp.normalize_plan({"scenes": [_scene(duration_seconds=duration, shots=shots)]}, clip_cap=30)["scenes"][0]["shots"]
        assert sum(s["seconds"] for s in planned) == duration, duration
        assert all(s["seconds"] >= 2 for s in planned), duration


def test_too_many_shots_for_a_short_scene_are_dropped_not_merged_into_a_slow_shot():
    many = _shots(*[(1, f"Shot idea {i}") for i in range(8)])
    scene = sp.normalize_plan({"scenes": [_scene(duration_seconds=6, shots=many)]}, clip_cap=30)["scenes"][0]
    assert len(scene["shots"]) == 3 and [s["seconds"] for s in scene["shots"]] == [2, 2, 2]
    assert scene["shots"][-1]["description"] == "Shot idea 2"


def test_slow_cuts_are_flagged_so_the_producer_sees_the_problem():
    one_long = _shots((12, "A man works at a laptop."))
    plan = sp.normalize_plan({"scenes": [_scene(duration_seconds=12, shots=one_long)]}, clip_cap=30)
    assert any("12s single shot" in w for w in plan["warnings"])
    legacy = sp.normalize_plan({"scenes": [_scene(duration_seconds=12, visual_direction="One long slow take of a man at a laptop.")]}, clip_cap=30)
    assert any("one 12s shot with no cuts" in w for w in legacy["warnings"])


def test_shot_lines_do_not_confuse_the_systems_scene_and_voiceover_parsers():
    shots = _shots((3, "Close-up: owner snaps laptop shut."), (3, "Overhead: parcels slide along a bench."), (3, "Wide: a shopper abandons a cart."))
    raw = {"scenes": [_scene(duration_seconds=9, shots=shots), _scene(title="Two", duration_seconds=8, shots=_shots((4, "Macro: coins drop."), (4, "Street: crowd crosses.")))]}
    plan = sp.build_script_plan(raw, clip_cap=30, script_text="Scene 1 (9s). Scene 2 (8s).")
    prompt = plan["canonical_prompt"]
    assert "Shot 2 (3s):" in prompt and "Pace: energetic" in prompt
    assert explicit_shot_windows(prompt) == [(0.0, 9.0), (9.0, 17.0)]  # shot lines are not read as scenes
    assert [(a, b) for a, b, _ in extract_voiceover_events(prompt, duration_seconds=17)] == [(0.0, 9.0), (9.0, 17.0)]
    assert "ON-SCREEN TEXT" not in prompt


def test_closing_split_keeps_the_lead_in_shot_list_and_refits_it_to_the_shorter_scene():
    row = _closing()
    row.pop("visual_direction", None)
    row["shots"] = _shots((3, "Strategist hands over a printed summary."), (3, "Close-up: a pen ticks a checklist."), (4, "Wide: team laughs around a table."))
    lead, cta = sp.normalize_plan({"scenes": [row]}, clip_cap=30)["scenes"]
    assert lead["duration_seconds"] == 6 and sum(s["seconds"] for s in lead["shots"]) == 6
    assert all(s["seconds"] >= 2 for s in lead["shots"])
    assert "Strategist hands over" in lead["visual_direction"]
    assert cta["visual_direction"] == sp.EMPTY_BACKGROUND and cta["shots"] == []
    # shots that describe the end card itself are swapped for the carry-on line
    bad = _closing()
    bad.pop("visual_direction", None)
    bad["shots"] = _shots((3, "Premium end card with the logo on the left."), (3, "A laptop on the right."))
    lead2, _ = sp.normalize_plan({"scenes": [bad]}, clip_cap=30)["scenes"]
    assert lead2["visual_direction"] == sp.LEAD_IN_CONTINUATION and lead2["shots"] == []


_DULL = [
    "Close-up of the owner at a laptop, frowning.",
    "Medium shot over the owner's shoulder as the owner scrolls the laptop.",
    "Overhead of the owner's hands on the laptop trackpad.",
    "Wide shot of the owner leaning back from the laptop.",
    "Close-up of the owner's face reflecting the laptop glow.",
]
_VARIED = [
    "Close-up: a store owner snaps a laptop shut, jaw tight.",
    "Overhead: parcels slide along a packing bench as a courier scans one.",
    "Street: a shopper scrolls her phone on a tram, thumb flicking past a product.",
    "Macro: coins drip from a jar onto a wooden counter, one by one.",
    "Low angle: a warehouse worker pushes a cart of boxes past tall shelves.",
]


def _plan_with_shots(descriptions, voiceover="Running an online store? How much of your budget is going to waste?"):
    scenes = []
    for i in range(0, len(descriptions), 3):
        chunk = descriptions[i : i + 3]
        scenes.append(_scene(title=f"Scene {i // 3 + 1}", duration_seconds=3 * len(chunk), voiceover=voiceover, shots=_shots(*[(3, d) for d in chunk])))
    return sp.build_script_plan({"scenes": scenes}, clip_cap=30, script_text="durations: 9s, 6s, 3s")


def test_a_film_that_shows_the_same_person_and_prop_in_most_shots_is_flagged():
    dull = _plan_with_shots(_DULL)
    assert dull["repetition"] and dull["repetition"]["word"] in {"owner", "laptop"}
    assert any("may feel repetitive" in w for w in dull["warnings"])
    varied = _plan_with_shots(_VARIED)
    assert varied["repetition"] is None
    assert not any("repetitive" in w for w in varied["warnings"])


def test_words_the_voiceover_uses_are_the_topic_not_a_lazy_repeat():
    serum = [
        "Close-up: serum drips from a glass pipette.",
        "Hands: serum pressed onto a cheek in a bright bathroom.",
        "Macro: serum beads on a marble counter.",
        "Wide: a friend laughs, serum on the shelf behind her.",
        "Street: a courier carries a serum box up the steps.",
    ]
    topic = _plan_with_shots(serum, voiceover="Meet our new serum, the serum everyone is talking about.")
    assert topic["repetition"] is None  # "serum" is in the voiceover: the topic, not a lazy repeat
    # the same word with a voiceover that never says it IS a repeat
    assert _plan_with_shots(serum, voiceover="Meet the one thing everyone is talking about right now.")["repetition"]["word"] == "serum"


def test_planner_asks_for_one_rewrite_when_the_shots_repeat_and_keeps_the_better_plan(monkeypatch):
    from app.services import image_prompt_service

    def raw(descriptions):
        scenes = []
        for i in range(0, len(descriptions), 3):
            chunk = descriptions[i : i + 3]
            scenes.append(_scene(title=f"Scene {i // 3 + 1}", duration_seconds=3 * len(chunk), shots=_shots(*[(3, d) for d in chunk])))
        return json.dumps({"scenes": scenes})

    client = _FakeClient([raw(_DULL), raw(_VARIED)])
    monkeypatch.setattr(image_prompt_service, "_get_openrouter_client", lambda: client)
    monkeypatch.setattr(sp.settings, "OPENROUTER_API_KEY", "test-key", raising=False)
    plan = asyncio.run(sp.plan_script(script_text="Scene 1 ...", model_slug="m", clip_cap=30))
    assert client.calls == 2 and plan["repetition"] is None  # the varied rewrite won
    assert "REVISION REQUEST" in client.last["messages"][1]["content"]
    # if the rewrite is no better, the first plan is kept and returned (never worse, never a third call)
    client2 = _FakeClient([raw(_DULL), raw(_DULL)])
    monkeypatch.setattr(image_prompt_service, "_get_openrouter_client", lambda: client2)
    plan2 = asyncio.run(sp.plan_script(script_text="Scene 1 ...", model_slug="m", clip_cap=30))
    assert client2.calls == 2 and plan2["repetition"] is not None
    # a failed rewrite call must not lose the first plan
    client3 = _FakeClient([raw(_DULL), RuntimeError("boom")])
    monkeypatch.setattr(image_prompt_service, "_get_openrouter_client", lambda: client3)
    assert asyncio.run(sp.plan_script(script_text="Scene 1 ...", model_slug="m", clip_cap=30))["scenes"]


def test_a_duration_the_model_claims_is_the_scripts_must_really_appear_in_the_script():
    line = " ".join(["word"] * 27)  # 27 words need about 11-12 seconds
    claimed = {"scenes": [_scene(duration_source="script", duration_seconds=8, voiceover=line)]}
    # the script never says 8 seconds: the model made it up, so the length follows the voiceover
    invented = sp.normalize_plan(claimed, clip_cap=30, script_text="SCENE 3 - AUDIT. Voiceover: lots of words")
    assert invented["scenes"][0]["duration_seconds"] == 12 and invented["scenes"][0]["duration_source"] == "estimated"
    assert not any("rushed or cut off" in w for w in invented["warnings"])
    # the script really says it: kept, and a too-short line is still flagged to the producer
    stated = sp.normalize_plan(claimed, clip_cap=30, script_text="SCENE 3 (8s) Voiceover: lots of words")
    assert stated["scenes"][0]["duration_seconds"] == 8 and stated["scenes"][0]["duration_source"] == "script"
    assert any("rushed or cut off" in w for w in stated["warnings"])


def test_every_way_a_script_writes_a_duration_counts_as_evidence():
    ev = sp._duration_evidence
    assert 9 in ev("SCENE 1 | 0-9 SECONDS") and 9 in ev("0:00-0:09 Hook") and 8 in ev("Scene (8s)")
    assert 12 in ev("about 12 seconds") and 15 in ev("0:15-0:30") and 6 in ev("[0:06 - 0:12]")
    assert ev("no numbers here, 12 shoppers") == set()  # "12 shoppers" is not a duration


def test_durations_that_add_up_to_the_stated_total_are_trusted():
    scenes = [_scene(duration_source="script", duration_seconds=s, voiceover=" ".join(["word"] * 10)) for s in (6, 6, 4, 4)]
    plan = sp.normalize_plan({"scenes": scenes}, clip_cap=30, script_text="Make a 20 second ad for a cafe.")
    assert [s["duration_seconds"] for s in plan["scenes"]] == [6, 6, 4, 4] and plan["total_seconds"] == 20
    # claims that miss the stated total and are not written anywhere in the script are not trusted
    off = sp.normalize_plan({"scenes": scenes}, clip_cap=30, script_text="Make a 40 second ad for a cafe.")
    assert all(s["duration_source"] == "estimated" for s in off["scenes"])


def test_the_prompt_tells_seedance_to_speak_from_the_first_frame_without_confusing_the_voiceover_reader():
    plan = _built()
    prompt = plan["canonical_prompt"]
    assert "speech starts on the very first frame (0:00) with no silent lead-in" in prompt
    cues = [line for line in prompt.splitlines() if line.startswith("SPEECH CUE:")]
    assert len(cues) == 3 and all("first frame of this scene" in c for c in cues)  # one per scene that is spoken
    # the extra lines must not be mistaken for spoken lines: windows and lines are exactly the scenes'
    events = extract_voiceover_events(prompt, duration_seconds=24)
    assert [(a, b) for a, b, _ in events] == [(0.0, 8.0), (8.0, 15.0), (15.0, 24.0)]
    assert all("first frame" not in text and "silent lead-in" not in text for _, _, text in events)
    assert explicit_shot_windows(prompt) == [(0.0, 8.0), (8.0, 15.0), (15.0, 24.0)]
    # a silent film gets no speech instructions at all
    silent = sp.build_script_plan({"scenes": [_scene(voiceover="", speech="none")]}, clip_cap=30, script_text="x")
    assert "SPEECH CUE" not in silent["canonical_prompt"] and "Audio: speech" not in silent["canonical_prompt"]
    ugc = sp.build_script_plan({"scenes": [_scene(speech="on_camera")]}, clip_cap=30, script_text="x (8s)")
    assert "the person starts speaking on the first frame" in ugc["canonical_prompt"]


def test_footage_that_asks_for_readable_screens_or_logos_is_warned():
    risky = _scene(visual_direction="The laptop screen clearly shows a professional analytics interface with a logo.")
    safe = _scene(
        title="Safe",
        visual_direction="The laptop screen glows softly and is out of focus; no readable text or logos anywhere.",
    )
    plan = sp.normalize_plan({"scenes": [risky, safe]}, clip_cap=30)
    flagged = [w for w in plan["warnings"] if "garbled readable text" in w]
    assert len(flagged) == 1 and "interface" in flagged[0] and "logo" in flagged[0]
    assert "Safe" not in flagged[0]


def test_canonical_prompt_carries_the_scripts_voice_into_the_existing_voice_lock():
    prompt = _built()["canonical_prompt"]
    lower = prompt.lower()
    # the same checks the existing voice lock / speech code run on the brief
    assert re.search(r"\b(?:female voice|female presenter|woman presenter)\b", lower)
    assert not re.search(r"\b(?:male voice|male presenter|man presenter)\b", lower)
    assert "australian" in lower
    assert _built()["voice"]["source"] == "script"


def test_a_script_that_names_no_voice_still_gets_the_australian_english_voice():
    raw = {"scenes": [_scene()]}
    plan = sp.build_script_plan(raw, clip_cap=30, script_text="SCENE 1 ...")
    assert plan["voice"]["source"] == "default" and plan["voice"]["gender"] == ""
    assert "Australian English voice, natural off-camera narration" in plan["canonical_prompt"]
    # no gender named, so the existing lock keeps its own default (it only reads "female/male voice")
    lower = plan["canonical_prompt"].lower()
    assert not re.search(r"\b(?:female voice|male voice)\b", lower)
    assert "australian" in lower


def test_footage_directions_carry_no_text_or_voiceover():
    plan = _built()
    assert "never show readable text" in plan["canonical_prompt"]
    assert plan["scenes"][0]["visual_direction"] not in (plan["scenes"][0]["voiceover"],)


def test_planner_defaults_to_gpt_41_and_honours_an_explicit_pick():
    assert sp.script_plan_model(None) == "openai/gpt-4.1"
    assert sp.script_plan_model("auto") == "openai/gpt-4.1"
    assert sp.script_plan_model("  ") == "openai/gpt-4.1"
    assert sp.script_plan_model("google/gemini-2.5-pro") == "google/gemini-2.5-pro"
    # an unknown / retired slug never reaches the provider
    assert sp.script_plan_model("anthropic/claude-sonnet-4") in {
        "openai/gpt-4.1",
        "anthropic/claude-sonnet-4.6",
    }


# ── the LLM call ────────────────────────────────────────────────────────────


class _FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls += 1
                outer.last = kwargs
                reply = outer.replies.pop(0)
                if isinstance(reply, Exception):
                    raise reply
                message = type("M", (), {"content": reply})()
                return type("C", (), {"choices": [type("Ch", (), {"message": message})()]})()

        self.chat = type("Chat", (), {"completions": _Completions()})()


def _run_plan(monkeypatch, replies, script="Voice: Australian English female voice.\nScene 1 ..."):
    from app.services import image_prompt_service

    client = _FakeClient(replies)
    monkeypatch.setattr(image_prompt_service, "_get_openrouter_client", lambda: client)
    monkeypatch.setattr(sp.settings, "OPENROUTER_API_KEY", "test-key", raising=False)
    result = asyncio.run(sp.plan_script(script_text=script, model_slug="m", clip_cap=30))
    return result, client


def test_plan_script_end_to_end_with_fenced_json(monkeypatch):
    payload = json.dumps({"title": "T", "global_style": "warm", "scenes": [_scene()]})
    result, client = _run_plan(monkeypatch, [f"```json\n{payload}\n```"])
    assert result["scenes"][0]["title"] == "The hook"
    assert "female voice" in result["canonical_prompt"]
    assert "30 seconds" in client.last["messages"][1]["content"]
    assert client.calls == 1


def test_plan_script_retries_once_on_unreadable_answer(monkeypatch):
    payload = json.dumps({"scenes": [_scene()]})
    result, client = _run_plan(monkeypatch, ["sorry, no json", payload])
    assert client.calls == 2 and result["scenes"]


def test_plan_script_gives_clear_errors(monkeypatch):
    with pytest.raises(ValueError, match="could not be read"):
        _run_plan(monkeypatch, ["nope", "still nope"])
    with pytest.raises(ValueError, match="could not be reached"):
        _run_plan(monkeypatch, [RuntimeError("boom"), RuntimeError("boom")])
    with pytest.raises(ValueError, match="Add a script"):
        asyncio.run(sp.plan_script(script_text=" ", model_slug="m", clip_cap=30))
    with pytest.raises(ValueError, match="too long"):
        asyncio.run(sp.plan_script(script_text="x" * (sp.MAX_SCRIPT_CHARS + 1), model_slug="m", clip_cap=30))
