"""'Exact brand fonts': the app fetches the Brand Kit font and draws the on-image text itself."""

import asyncio
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from app.core.config import settings
from app.services import ad_image_design as ad
from app.services import ad_image_logo as al
from app.services import ad_image_text as at
from app.services import brand_fonts as bf


def _system_font() -> Path:
    import matplotlib

    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    pytest.skip("no TrueType font available on this machine")


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    from app.services.file_service import file_service

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_service, "upload_dir", tmp_path)
    return tmp_path


# ── fetching the saved font ─────────────────────────────────────────────────


class _Response:
    def __init__(self, status=200, text="", content=b""):
        self.status_code, self.text, self.content = status, text, content


class _FakeGoogle:
    """Stands in for fonts.googleapis.com / fonts.gstatic.com."""

    def __init__(self, families: dict[str, bytes]):
        self.families, self.calls = families, []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params, (headers or {}).get("User-Agent")))
        if "googleapis" in url:
            family = params["family"].split(":")[0]
            if family not in self.families:
                return _Response(400)
            return _Response(text=f"@font-face {{ src: url(https://fonts.gstatic.com/{family.replace(' ', '')}.ttf) format('truetype'); }}")
        name = url.rsplit("/", 1)[-1].removesuffix(".ttf")
        family = next((f for f in self.families if f.replace(" ", "") == name), None)
        return _Response(content=self.families[family]) if family else _Response(404)

    def close(self):
        pass


def test_family_names_are_made_safe_for_a_url():
    assert bf.clean_family("Cormorant Garamond") == "Cormorant Garamond"
    assert bf.clean_family("Open Sans; DROP TABLE") == "Open Sans DROP TABLE"
    assert bf.clean_family("../../etc/passwd") == "etc passwd"
    assert bf.clean_family(None) == "" and bf.clean_family("   ") == ""


def test_a_google_font_is_fetched_once_with_the_old_browser_header_and_then_served_from_disk(uploads):
    data = _system_font().read_bytes()
    google = _FakeGoogle({"Cormorant Garamond": data})
    first = bf.font_file("Cormorant Garamond", client=google)
    assert first and first.name == "cormorant-garamond-700.ttf" and first.read_bytes() == data
    assert google.calls[0][2] == "Mozilla/4.0"  # an old browser makes Google send plain TrueType, which Pillow reads
    calls = len(google.calls)
    assert bf.font_file("cormorant garamond", client=google) == first and len(google.calls) == calls  # no second download


def test_an_unknown_family_gives_none_and_is_not_retried_every_time(uploads):
    google = _FakeGoogle({})
    assert bf.font_file("My Custom Brand Font", client=google) is None
    calls = len(google.calls)
    assert bf.font_file("My Custom Brand Font", client=google) is None and len(google.calls) == calls
    assert bf.font_file("", client=google) is None


def test_a_file_that_is_not_a_font_is_rejected(uploads):
    google = _FakeGoogle({"Fake Font": b"<html>not a font</html>" * 100})
    assert bf.font_file("Fake Font", client=google) is None
    assert not list(bf.cache_dir().glob("fake-font-*.ttf"))


def test_the_pair_falls_back_to_the_heading_font_when_the_body_font_is_missing(uploads):
    data = _system_font().read_bytes()
    google = _FakeGoogle({"Cormorant Garamond": data})
    pair = bf.load_pair("Cormorant Garamond", "Unfetchable Sans", client=google)
    assert pair and pair["body"] == pair["heading"]
    assert bf.load_pair("Unfetchable Sans", "Cormorant Garamond", client=google) is None  # no heading font: not usable


# ── drawing the text ────────────────────────────────────────────────────────


def _photo(colour, size=(800, 800)):
    return Image.new("RGB", size, colour)


def _draw(photo, **kw):
    font = _system_font()
    args = dict(hook="The one she'll wear every day", headline="Make it perfect", cta="Book a Consultation",
                primary="#DBB45A", secondary="#000000", heading_font=font, body_font=font)
    args.update(kw)
    return at.render(photo, **args)


def test_text_is_drawn_only_in_the_chosen_zone_and_the_rest_of_the_picture_is_untouched():
    base = _photo((90, 70, 60))
    bottom, info = _draw(base, zone="bottom")
    ramp = round(800 * at.RAMP_SHARE)  # the backing eases out a little beyond the zone, so the edge is soft
    cut = round(800 * (1 - at.ZONE_SHARE))
    untouched = cut - ramp - 12  # the first rows of an easing curve differ by a single level, so allow a margin
    assert untouched > 200  # most of the picture is left alone
    assert ImageChops.difference(base.crop((0, 0, 800, untouched)), bottom.crop((0, 0, 800, untouched))).getbbox() is None
    assert ImageChops.difference(base.crop((0, cut, 800, 800)), bottom.crop((0, cut, 800, 800))).getbbox() is not None
    top, _ = _draw(base, zone="top")
    cut_top = round(800 * at.ZONE_SHARE) + ramp + 12
    assert ImageChops.difference(base.crop((0, cut_top, 800, 800)), top.crop((0, cut_top, 800, 800))).getbbox() is None
    assert info["zone"] == "bottom" and info["lines"][-1] == "Book a Consultation"


def test_the_cta_is_a_pill_in_the_brand_primary_colour_with_a_readable_label():
    out, info = _draw(_photo((60, 50, 45)), primary="#DBB45A")
    assert info["pill_colour"] == "#DBB45A"
    pixels = out.getdata()
    assert sum(1 for p in pixels if max(abs(a - b) for a, b in zip(p, (0xDB, 0xB4, 0x5A))) < 6) > 800  # a real pill
    deep, _ = _draw(_photo((60, 50, 45)), primary="#072032")
    assert any(sum(p) < 90 for p in deep.getdata())  # navy pill exists
    # the label is dark on a light pill and light on a dark pill
    assert _draw(_photo((60, 50, 45)), primary="#FFFFFF")[1]["pill_colour"] == "#FFFFFF"


def test_text_colour_is_chosen_from_the_picture_under_it_so_it_stays_readable():
    # a short hook has nothing to highlight, so it is set in the brand colour where that reads
    on_dark = _draw(_photo((25, 25, 30)), primary="#DBB45A", hook="Perfect rings")[1]
    on_bright = _draw(_photo((245, 242, 235)), primary="#DBB45A", hook="Perfect rings")[1]
    assert on_dark["bright_zone"] is False and on_dark["hook_colour"] == "#DBB45A"  # gold reads on dark
    assert on_bright["bright_zone"] is True and on_bright["hook_colour"] != "#DBB45A"  # gold would not: neutral dark used
    assert at._contrast(at._rgb(on_bright["hook_colour"]), (246, 246, 244)) >= 4.5
    # a longer hook is plain and readable, with its payoff words on a block of the brand colour
    long_dark = _draw(_photo((25, 25, 30)), primary="#DBB45A")[1]
    long_bright = _draw(_photo((245, 242, 235)), primary="#DBB45A")[1]
    assert long_dark["hook_colour"] == "#FFFFFF" and long_dark["highlight_colour"] == "#DBB45A"
    assert at._contrast(at._rgb(long_bright["hook_colour"]), (246, 246, 244)) >= 4.5 and long_bright["highlight"]


def test_long_copy_shrinks_to_fit_and_never_runs_past_the_margins():
    hook = "An extremely long attention grabbing opening line that would never fit at the starting size"
    out, info = _draw(_photo((30, 30, 30)), hook=hook, headline=hook, cta="Book a Consultation Today With Us")
    margin = round(800 * at.MARGIN_SHARE)
    base = _photo((30, 30, 30))
    side = lambda img: img.crop((0, 400, margin - 6, 800))  # noqa: E731 - the empty left margin strip
    # only the soft scrim changes the margin: no letters (which would be bright gold or white)
    assert max(max(p) for p in side(out).getdata()) < 120
    assert len([line for line in info["lines"] if line.split()[0] in hook.split()[:2]]) <= 6


def test_missing_pieces_are_simply_left_out():
    _, no_cta = _draw(_photo((30, 30, 30)), cta="")
    assert "Book a Consultation" not in no_cta["lines"]
    _, only_cta = _draw(_photo((30, 30, 30)), hook="", headline="")
    assert only_cta["lines"] == ["Book a Consultation"]


def test_the_alignment_option_centres_the_lines():
    left, _ = _draw(_photo((30, 30, 30)), align="left")
    centre, _ = _draw(_photo((30, 30, 30)), align="center")
    assert ImageChops.difference(left, centre).getbbox() is not None


def test_text_goes_at_the_bottom_unless_the_logo_is_in_a_bottom_corner():
    assert at.zone_for_logo("top_right") == "bottom" and at.zone_for_logo("auto") == "bottom"
    assert at.zone_for_logo("") == "bottom" and at.zone_for_logo("none") == "bottom"
    assert at.zone_for_logo("bottom_left") == "top" and at.zone_for_logo("bottom_right") == "top"


# ── the text-free picture the model is asked for ────────────────────────────

SCENE = "A woman rests her hand on a table, ring on her finger, warm natural light and a calm mood."


def test_exact_mode_asks_for_a_picture_with_no_writing_and_a_calm_band_for_the_text():
    prompt, _ = ad.compose(
        scene_source=SCENE, seed="b", index=0, hook="The one she'll wear every day", headline="Make it perfect",
        cta="Book a Consultation", primary="#DBB45A", secondary="#000000", font_heading="Cormorant Garamond",
        font_body="Open Sans", exact_text=True, text_zone="bottom",
    )
    assert "No text, letters, numbers or buttons anywhere" in prompt and "bottom 40% of the frame" in prompt
    assert 'headline "' not in prompt and "button reading" not in prompt and "Typography" not in prompt
    assert "Cormorant" not in prompt and "#DBB45A" in prompt  # the model only needs the colours
    top, _ = ad.compose(scene_source=SCENE, seed="b", index=0, exact_text=True, text_zone="top")
    assert "top 40% of the frame" in top


def test_the_logo_guard_does_not_delete_the_text_free_instruction():
    """Regression: the guard drops any sentence containing 'logo', and the instruction used to say 'logos'."""
    prompt, _ = ad.compose(scene_source=SCENE, seed="b", index=0, hook="x y", cta="Go", exact_text=True)
    final, _ = al.prepare_prompt(prompt, "top_right", "Adoria Jewels")
    assert "No text, letters, numbers or buttons anywhere" in final and "bottom 40% of the frame" in final
    photo, _ = ad.compose(scene_source=SCENE, seed="b", index=0, photo_only=True)
    assert "No text, letters or numbers anywhere on the image; a clean photo only." in al.guard_prompt(photo, "Adoria Jewels")


def test_the_setting_switches_the_designed_prompt_on_by_itself():
    assert ad.enabled({"image_text_mode": "exact"}, {}, "auto", "auto")
    assert not ad.enabled({"image_text_mode": "exact"}, {}, "jewellery_luxury", "auto")  # a chosen style still wins
    assert not ad.enabled({}, {}, "auto", "auto")
    assert at.requested({"image_text_mode": "exact"}, {}) and not at.requested({}, {}) and not at.requested({"image_text_mode": ""}, {})


# ── the job's helpers: never lose a picture ─────────────────────────────────


def _result(uploads, name="img.png", colour=(40, 40, 50)):
    folder = uploads / "t" / "generated"
    folder.mkdir(parents=True, exist_ok=True)
    _photo(colour).save(folder / name)
    return {"status": "done", "url": f"/files/t/generated/{name}", "model": "m", "provider": "openai"}


def _run(coro):
    return asyncio.run(coro)


def test_the_text_is_added_to_a_finished_image_and_the_plain_one_is_kept(uploads):
    font = _system_font()
    result = _result(uploads)
    out = _run(at.overlay_result(
        result, fonts={"heading": font, "body": font}, hook="The one she'll wear", headline="Make it perfect",
        cta="Book a Consultation", primary="#DBB45A", secondary="#000000", tenant_id="t",
    ))
    assert out["text_mode"] == "exact" and out["url"] != result["url"] and out["url_without_text"] == result["url"]
    assert out["text_lines"][-1] == "Book a Consultation"
    assert Image.open(uploads / out["url"].removeprefix("/files/")).size == (800, 800)


def test_failed_remote_and_empty_results_are_left_alone_and_errors_keep_the_picture(uploads, monkeypatch):
    font = _system_font()
    kw = dict(fonts={"heading": font, "body": font}, hook="Hello", headline="", cta="Go", primary="", secondary="", tenant_id="t")
    assert _run(at.overlay_result({"status": "failed", "url": None}, **kw))["status"] == "failed"
    remote = {"status": "done", "url": "https://cdn.example.com/a.png"}
    assert _run(at.overlay_result(remote, **kw)) == remote
    assert _run(at.overlay_result("boom", **kw)) == "boom"
    empty = _result(uploads, "e.png")
    assert _run(at.overlay_result(empty, **{**kw, "hook": "", "cta": ""})) == empty

    def explode(**_):
        raise OSError("disk full")

    monkeypatch.setattr(at, "apply_text_overlay", explode)
    kept = _run(at.overlay_result(_result(uploads, "k.png"), **kw))
    assert kept["url"].endswith("k.png") and kept["text_mode"] == "failed" and "disk full" in kept["warnings"][0]


def test_fonts_that_cannot_be_had_give_a_clear_note_so_the_model_draws_the_text(monkeypatch):
    assert _run(at.load_fonts("", "Open Sans")) == (None, "No heading font is saved on the Brand page, so the image model drew the text.")
    monkeypatch.setattr(bf, "load_pair", lambda heading, body: None)
    fonts, note = _run(at.load_fonts("My Custom Font", "Open Sans"))
    assert fonts is None and "'My Custom Font' could not be fetched" in note and "Google font" in note
    font = _system_font()
    monkeypatch.setattr(bf, "load_pair", lambda heading, body: {"heading": font, "body": font})
    assert _run(at.load_fonts("Cormorant Garamond", "Open Sans")) == ({"heading": font, "body": font}, "")


# ── what people actually type in the Brand page's font box ──────────────────


@pytest.mark.parametrize(
    "typed,family,weight",
    [
        ("Oswald", "Oswald", None),
        ("Oswald, 700", "Oswald", 700),  # the box's own hint is "Inter, 700"
        ("Arimo, 400", "Arimo", 400),
        ("Arimo, Regular", "Arimo", 400),
        ("Open Sans Bold", "Open Sans", 700),
        ("Inter 600", "Inter", 600),
        ("Roboto Condensed, 700", "Roboto Condensed", 700),
        ("Oswald, sans-serif", "Oswald", None),  # a CSS fallback is ignored
        ('"Playfair Display", serif', "Playfair Display", None),
        ("Source Sans 3", "Source Sans 3", None),  # a family whose name ends in a digit is not a weight
        ("Bebas Neue", "Bebas Neue", None),
        ("  ", "", None),
        (None, "", None),
    ],
)
def test_the_font_box_is_read_the_way_people_type_it(typed, family, weight):
    assert bf.parse_font_spec(typed) == (family, weight)


def test_a_font_typed_with_a_weight_is_found_and_the_asked_weight_is_tried_first(uploads):
    data = _system_font().read_bytes()
    google = _FakeGoogle({"Oswald": data})
    path = bf.font_file("Oswald, 600", client=google)
    assert path and path.name == "oswald-600.ttf"
    assert google.calls[0][1]["family"] == "Oswald:600"  # the weight they typed, asked for first
    pair = bf.load_pair("Oswald, 700", "Oswald, 400", client=_FakeGoogle({"Oswald": data}))
    assert pair and pair["heading"].name == "oswald-700.ttf" and pair["body"].name == "oswald-400.ttf"


def test_a_typed_weight_never_leaks_into_the_font_description_or_the_failure_note(monkeypatch):
    from app.services import ad_image_brand as ab

    assert ab.describe_font("Oswald, 700") == "Oswald (a tall condensed sans-serif)"
    assert ab.describe_font("Cormorant Garamond, 700").startswith("Cormorant Garamond (an elegant")
    monkeypatch.setattr(bf, "load_pair", lambda heading, body: None)
    _, note = _run(at.load_fonts("My Custom Font, 700", ""))
    assert "'My Custom Font' could not be fetched" in note and "700" not in note


def test_a_headline_in_the_brand_colour_stays_readable_on_a_background_the_model_painted_in_that_colour():
    """Regression: the model made an orange field and the orange headline vanished into it."""
    orange_field = _photo((252, 96, 44))
    out, info = _draw(orange_field, primary="#FC602C")
    assert info["hook_contrast"] >= 3.0  # measured against what is really under the headline
    other = _draw(_photo((25, 25, 30)), primary="#FC602C", hook="Stop bleeding")[1]
    assert other["hook_contrast"] >= 3.0 and other["hook_colour"] == "#FC602C"  # short hook: brand colour, it reads
    # and when the brand colour cannot be read on the picture at all, a neutral is used instead
    white_field = _draw(_photo((255, 255, 255)), primary="#FFFFFF", hook="Stop bleeding")[1]
    assert white_field["hook_contrast"] >= 3.0 and white_field["hook_colour"] != "#FFFFFF"


def test_the_backing_eases_into_the_picture_without_a_hard_edge():
    base = _photo((120, 90, 70))
    out, _ = _draw(base, zone="bottom")
    column = [out.getpixel((10, y))[0] for y in range(250, 560)]  # the empty left margin: no letters in the way
    steps = [abs(b - a) for a, b in zip(column, column[1:])]
    assert max(steps) <= 6  # the picture darkens gradually, never in a single jump
    assert column[-1] < column[0]  # and it does darken toward the text


# ── layout variety: each creative gets its own look, stable on regenerate ──────────────────────────────────


def test_each_creative_gets_a_different_text_layout_and_it_is_stable():
    layouts = [at.layout_for("brief-9", i) for i in range(8)]
    assert len(set(layouts)) == 8 and {a for a, _ in layouts} == {"left", "center", "right"}
    assert {b for _, b in layouts} == {"fade", "band", "card"}
    assert [at.layout_for("brief-9", i) for i in range(8)] == layouts


@pytest.mark.parametrize("align", ["left", "center", "right"])
@pytest.mark.parametrize("backing", ["fade", "band", "card"])
def test_every_alignment_and_backing_draws_the_text_inside_the_picture(align, backing):
    from PIL import Image

    font = _system_font()
    base = Image.new("RGB", (800, 800), (120, 150, 190))
    out, info = at.render(
        base, hook="Still putting off **Google Ads**?", headline="Take the next step", cta="Get Free Quote",
        primary="#A4D36B", secondary="#072032", heading_font=font, body_font=font, zone="bottom", align=align, backing=backing,
    )
    assert out.size == (800, 800) and info["align"] == align and info["backing"] == backing
    assert out.tobytes() != base.convert("RGB").tobytes()
    if backing == "band":  # a solid band in the brand colour runs edge to edge under the text
        corner = out.getpixel((2, 797))[:3]
        assert all(abs(a - b) <= 4 for a, b in zip(corner, (164, 211, 107)))
