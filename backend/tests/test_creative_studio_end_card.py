import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.services import creative_studio_end_card as ec
from app.services import creative_studio_script_plan as sp
from app.services.ffmpeg_util import ffmpeg_executable, probe_video_duration

MAGENTA = (255, 0, 255, 255)


def _logo(w=400, h=100, colour=MAGENTA):
    return Image.new("RGBA", (w, h), colour)


def _alpha_box(img):
    return img.getchannel("A").getbbox()


def _inside(inner, outer, slack=0):
    return inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack and inner[2] <= outer[2] + slack and inner[3] <= outer[3] + slack


# ── drawing the card ────────────────────────────────────────────────────────


def test_portrait_card_stays_inside_the_safe_area_and_nothing_is_drawn_outside_it():
    card, info = ec.render_end_card(
        (1080, 1920), logo=_logo(), headline="FREE GOOGLE ADS AUDIT",
        sublines=["NO FEES. NO OBLIGATION."], button_text="BOOK YOUR FREE AUDIT",
    )
    assert card.size == (1080, 1920) and info["portrait"] is True
    box = info["card_box"]
    top, bottom = info["safe_zone"]
    assert top >= 1920 * 0.12 - 1 and bottom <= 1920 * 0.80 + 1  # clear of the app UI strips
    assert box[1] >= top and box[3] <= bottom
    assert box[0] >= 1080 * 0.04 and box[2] <= 1080 * 0.96
    # every visible pixel belongs to the card: nothing leaks outside it
    assert _inside(_alpha_box(card), box)


def test_landscape_card_sits_in_the_left_column_leaving_the_right_side_free():
    card, info = ec.render_end_card(
        (1920, 1080), logo=_logo(), headline="FREE GOOGLE ADS AUDIT",
        sublines=["NO FEES. NO OBLIGATION."], button_text="BOOK YOUR FREE AUDIT",
    )
    assert info["portrait"] is False
    assert info["card_box"][2] <= 1920 * 0.55
    assert _inside(_alpha_box(card), info["card_box"])


def test_logo_is_scaled_without_stretching_or_recolouring():
    card, _ = ec.render_end_card((1080, 1920), logo=_logo(400, 100), headline="Headline", sublines=[], button_text="")
    px = card.load()
    xs, ys, other = [], [], 0
    for y in range(card.height):
        for x in range(card.width):
            if px[x, y] == MAGENTA:
                xs.append(x)
                ys.append(y)
            elif px[x, y][:3] == (255, 0, 255):
                other += 1
    width, height = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    assert abs(width / height - 4.0) < 0.08  # aspect ratio kept
    assert other == 0  # no blended/tinted magenta: the logo's pixels are untouched
    # a tall logo keeps its own shape too
    card2, _ = ec.render_end_card((1080, 1920), logo=_logo(120, 240), headline="Headline", sublines=[], button_text="")
    px2 = card2.load()
    pts = [(x, y) for y in range(card2.height) for x in range(card2.width) if px2[x, y] == MAGENTA]
    w2 = max(p[0] for p in pts) - min(p[0] for p in pts) + 1
    h2 = max(p[1] for p in pts) - min(p[1] for p in pts) + 1
    assert abs(w2 / h2 - 0.5) < 0.06


def test_transparent_padding_around_a_logo_is_trimmed_so_it_lines_up_with_the_text():
    padded = Image.new("RGBA", (600, 300), (0, 0, 0, 0))
    padded.paste(Image.new("RGBA", (300, 80), MAGENTA), (150, 110))  # empty margin all round
    card, info = ec.render_end_card((1080, 1920), logo=padded, headline="Headline", sublines=[], button_text="")
    px = card.load()
    xs = [x for y in range(card.height) for x in range(card.width) if px[x, y] == MAGENTA]
    pad = round((info["card_box"][2] - info["card_box"][0]) * 0.07)
    assert min(xs) == info["card_box"][0] + pad  # flush with the text column, not indented
    # a logo with nothing visible in it is treated as no logo instead of crashing
    empty, _ = ec.render_end_card((1080, 1920), logo=Image.new("RGBA", (50, 50), (0, 0, 0, 0)), headline="Headline", sublines=[], button_text="")
    assert empty.size == (1080, 1920)


def test_card_colour_suits_the_logo_not_the_other_way_round():
    _, dark_logo = ec.render_end_card((1080, 1920), logo=_logo(colour=(255, 255, 255, 255)), headline="Hi", sublines=[], button_text="")
    _, coloured = ec.render_end_card((1080, 1920), logo=_logo(colour=(10, 60, 200, 255)), headline="Hi", sublines=[], button_text="")
    _, no_logo = ec.render_end_card((1080, 1920), logo=None, headline="Hi", sublines=[], button_text="")
    assert dark_logo["theme"] == "dark"  # a white mark would vanish on a white card
    assert coloured["theme"] == "light" and no_logo["theme"] == "light"
    assert ec.is_light_mark(_logo(colour=(250, 250, 250, 255))) and not ec.is_light_mark(_logo(colour=(10, 60, 200, 255)))


def test_long_wrapped_text_shrinks_to_fit_and_never_gets_cut_off():
    long_headline = "Find out exactly where your Google Ads budget is going and what to fix first this quarter"
    card, info = ec.render_end_card(
        (1080, 1920), logo=_logo(), headline=long_headline,
        sublines=["No fees, no obligation, and no pressure to work with us at any point"], button_text="BOOK YOUR FREE AUDIT",
    )
    assert info["scale"] <= 1.0
    assert _inside(_alpha_box(card), info["card_box"])


def test_text_that_cannot_fit_is_rejected_with_a_clear_message():
    # one unbreakable word wider than the card, even at the smallest readable size
    with pytest.raises(ValueError, match="too long to fit"):
        ec.render_end_card((1080, 1920), logo=_logo(), headline="W" * 100, sublines=[], button_text="B")
    # a button label sits on one line, so a very long one cannot fit
    with pytest.raises(ValueError, match="too long to fit"):
        ec.render_end_card((1080, 1920), logo=_logo(), headline="Short", sublines=[], button_text="A VERY LONG BUTTON LABEL " * 4)
    # ordinary long sentences are NOT rejected: they wrap and shrink (covered above)
    card, info = ec.render_end_card((1080, 1920), logo=_logo(), headline="word " * 24, sublines=["x " * 50] * 3, button_text="B")
    assert _inside(_alpha_box(card), info["card_box"]) and info["scale"] < 1.0


def test_line_and_colour_validation():
    with pytest.raises(ValueError, match="headline"):
        ec.clean_lines("  ", [], "")
    with pytest.raises(ValueError, match="at most 3"):
        ec.clean_lines("h", ["a", "b", "c", "d"], "")
    with pytest.raises(ValueError, match="120 characters"):
        ec.clean_lines("h" * 121, [], "")
    assert ec.parse_hex_colour("#1D6FE8", "#000000") == (29, 111, 232)
    assert ec.parse_hex_colour("", "#2FA862") == (47, 168, 98)
    for bad in ("blue", "#12345", "#GGGGGG", "1D6FE8;rm"):
        with pytest.raises(ValueError):
            ec.parse_hex_colour(bad, "#000000")
    assert ec.clean_lines("  FREE   AUDIT ", [" a  b "], "  BOOK  ") == ("FREE AUDIT", ["a b"], "BOOK")


# ── the card's text comes from the script ───────────────────────────────────


def test_planner_hands_the_script_text_and_timing_to_the_end_card():
    row = sp_closing()
    plan = sp.build_script_plan({"scenes": [row]}, clip_cap=30, script_text="x")
    card = plan["end_card"]
    assert card["headline"] == "FREE GOOGLE ADS AUDIT"
    assert card["sublines"] == ["NO FEES. NO OBLIGATION."]
    assert card["button_text"] == "BOOK YOUR FREE AUDIT"
    cta = plan["scenes"][-1]
    assert card["start_seconds"] == cta["start"] and card["hold_seconds"] == 4.0
    # nothing to put on a card when the script has no end card
    none = sp.build_script_plan({"scenes": [sp_closing(plain=True)]}, clip_cap=30, script_text="x")
    assert none["end_card"] is None


def sp_closing(plain=False):
    row = {
        "title": "Offer and CTA",
        "duration_seconds": 10,
        "duration_source": "estimated",
        "voiceover": "You'll get clear recommendations, with no fees. Book your free audit with Traffic Radius.",
        "visual_direction": "The strategist smiles and hands over a printed summary.",
        "on_screen_text": ["FREE GOOGLE ADS AUDIT", "NO FEES. NO OBLIGATION.", "BOOK YOUR FREE AUDIT"],
        "edit_inserts": [] if plain else [{"starts_at_seconds": 0, "duration_seconds": 10, "kind": "end card", "note": "card"}],
        "closing_card": None if plain else {"line": "Book your free audit with Traffic Radius.", "note": "logo left, blue button"},
    }
    return row


# ── on a real video ─────────────────────────────────────────────────────────


needs_ffmpeg = pytest.mark.skipif(not ffmpeg_executable(), reason="ffmpeg is not installed")


def _make_video(path: Path, seconds=6, size="320x568"):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg_executable(), "-y", "-f", "lavfi", "-i", f"color=c=0x303840:s={size}:d={seconds}:r=24",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
        check=True, capture_output=True,
    )


def _frame(video: Path, at: float, out: Path) -> Image.Image:
    subprocess.run([ffmpeg_executable(), "-y", "-ss", f"{at}", "-i", str(video), "-frames:v", "1", str(out)], check=True, capture_output=True)
    return Image.open(out).convert("RGB")


def _white_share(img: Image.Image) -> float:
    data = list(img.resize((80, 142)).getdata())
    return sum(1 for r, g, b in data if r > 235 and g > 235 and b > 235) / len(data)


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.services.file_service import file_service

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_service, "upload_dir", tmp_path)
    monkeypatch.setattr(ec, "_load_logo", lambda *a, **k: _logo(300, 90, (10, 60, 200, 255)))
    return tmp_path


@needs_ffmpeg
def test_end_card_is_laid_over_only_the_last_seconds_and_audio_is_kept(uploads, tmp_path):
    source = uploads / "t1" / "generated" / "in.mp4"
    _make_video(source, seconds=6)
    result = ec.add_end_card_to_video(
        video_url="/files/t1/generated/in.mp4", tenant_id="t1",
        headline="FREE GOOGLE ADS AUDIT", sublines=["NO FEES. NO OBLIGATION."], button_text="BOOK YOUR FREE AUDIT",
        hold_seconds=3,
    )
    assert result["kind"] == "video" and result["logo_applied"] is True
    assert result["start_seconds"] == pytest.approx(3.0, abs=0.1) and result["hold_seconds"] == pytest.approx(3.0, abs=0.1)
    output = uploads / result["url"].removeprefix("/files/")
    assert output.is_file()
    assert probe_video_duration(output) == pytest.approx(probe_video_duration(source), abs=0.3)  # same length
    assert b"Audio" in subprocess.run([ffmpeg_executable(), "-i", str(output)], capture_output=True).stderr  # voice kept
    before = _frame(output, 1.0, tmp_path / "before.png")
    during = _frame(output, 5.0, tmp_path / "during.png")
    assert _white_share(before) < 0.02  # no card early in the video
    assert _white_share(during) > 0.15  # white card is there at the end
    assert (result["width"], result["height"]) == (1080, 1920) or result["width"] < result["height"]


@needs_ffmpeg
def test_preview_shows_the_card_on_the_real_frame_without_encoding_a_video(uploads):
    _make_video(uploads / "t1" / "generated" / "in.mp4", seconds=5)
    result = ec.add_end_card_to_video(
        video_url="/files/t1/generated/in.mp4", tenant_id="t1", headline="FREE GOOGLE ADS AUDIT",
        button_text="BOOK YOUR FREE AUDIT", preview=True,
    )
    assert result["kind"] == "preview" and result["url"].endswith(".png")
    image = Image.open(uploads / result["url"].removeprefix("/files/"))
    assert image.size == (result["width"], result["height"])
    assert _white_share(image.convert("RGB")) > 0.15


@needs_ffmpeg
def test_missing_logo_gives_a_text_only_card_with_a_warning_and_a_missing_video_a_clear_error(uploads, monkeypatch):
    _make_video(uploads / "t1" / "generated" / "in.mp4", seconds=5)
    monkeypatch.setattr(ec, "_load_logo", lambda *a, **k: None)
    result = ec.add_end_card_to_video(video_url="/files/t1/generated/in.mp4", tenant_id="t1", headline="Book now", preview=True)
    assert result["logo_applied"] is False and any("No brand logo" in w for w in result["warnings"])
    with pytest.raises(ValueError, match="could not be found"):
        ec.add_end_card_to_video(video_url="/files/t1/generated/nope.mp4", tenant_id="t1", headline="Book now")
    with pytest.raises(ValueError, match="too long to fit"):
        ec.add_end_card_to_video(video_url="/files/t1/generated/in.mp4", tenant_id="t1", headline="W" * 100, button_text="x", preview=True)
