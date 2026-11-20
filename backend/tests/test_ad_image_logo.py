import asyncio

import pytest
from PIL import Image, ImageChops, ImageDraw

from app.core.config import settings
from app.services import ad_image_logo as al
from app.services import creative_studio_still as still
from app.services import creative_studio_still_logo as sl

TENANT = "11111111-1111-1111-1111-111111111111"
W, H = 800, 800


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    from app.services.file_service import file_service

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_service, "upload_dir", tmp_path)
    return tmp_path


def _save(root, name, image):
    folder = root / "t" / "ads"
    folder.mkdir(parents=True, exist_ok=True)
    image.save(folder / name)
    return f"/files/t/ads/{name}"


def _local(root, url):
    return root / url.removeprefix("/files/")


def _logo(colour=(255, 255, 255, 255)):
    img = Image.new("RGBA", (400, 160), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((40, 40, 359, 119), fill=colour)
    return img


def _ad(root, name, bg=(20, 24, 40), busy=()):
    """A flat ad with stripes (like lines of text) in the corners named in ``busy``."""
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    for corner in busy:
        x0 = 20 if corner.endswith("left") else W - 230
        y0 = 20 if corner.startswith("top") else H - 130
        for i in range(0, 210, 8):
            draw.rectangle((x0 + i, y0, x0 + i + 3, y0 + 110), fill=(255, 255, 255))
    return _save(root, name, img)


def _result(url):
    return {"status": "done", "url": url, "model": "gpt-image", "provider": "openai"}


def _changed_corner(root, before_url, after_url):
    box = ImageChops.difference(Image.open(_local(root, before_url)).convert("RGB"), Image.open(_local(root, after_url)).convert("RGB")).getbbox()
    left, top, right, bottom = box
    return ("top" if top < H / 2 else "bottom") + "_" + ("left" if left < W / 2 else "right")


# ── which mode applies ──────────────────────────────────────────────────────


def test_modes_are_normalised_and_unknown_values_keep_the_old_behaviour():
    assert [al.normalize_mode(v) for v in ("Top-Right", "bottom left", "auto", "AUTO", "none", "off", "no logo")] == [
        "top_right", "bottom_left", "auto", "auto", "none", "none", "none"
    ]
    assert al.normalize_mode("") == al.normalize_mode(None) == al.normalize_mode("middle") == al.normalize_mode(5) == ""


def test_a_variants_own_choice_beats_the_campaign_and_empty_means_follow_the_campaign():
    campaign = {"image_logo_corner": "top_left"}
    assert al.resolve_mode({"logo_corner": "bottom_right"}, campaign, {}) == "bottom_right"
    assert al.resolve_mode({"logo_corner": ""}, campaign, {}) == "top_left"
    assert al.resolve_mode({}, {}, {"image_logo_corner": "auto"}) == "auto"
    assert al.resolve_mode(None, None, None) == ""  # nothing chosen: the old white-strip behaviour
    assert al.resolve_mode({"logo_corner": "none"}, campaign, {}) == "none"


# ── reading the prompt ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("Hero photo of a ring. Brand logo in the bottom right corner.", "bottom_right"),
        ("Put the logo top-left, headline centred", "top_left"),
        ("Lower left logo, big offer text", "bottom_left"),
        ("Hero photo. Brand Kit logo is composited in post.", ""),
    ],
)
def test_a_corner_the_prompt_asks_for_the_logo_is_found(prompt, expected):
    assert al.requested_corner(prompt) == expected


def test_corners_used_by_text_are_avoided_when_suggesting_one():
    assert al.occupied_corners("Headline in the top left, CTA button bottom right.") == {"top_left", "bottom_right"}
    assert al.occupied_corners("Headline across the top, CTA at the bottom.") == {"top_left", "top_right", "bottom_left", "bottom_right"}
    assert al.occupied_corners("Logo top left. Photo of a shoe.") == set()  # a logo sentence never counts as text
    assert al.suggest_corner("Headline in the top right. Offer badge bottom right.") == "top_left"
    assert al.suggest_corner("Headline across the top.") == "bottom_right"
    assert al.suggest_corner("A plain photo of a shoe.") == "top_right"  # usual first choice
    assert al.suggest_corner("Headline across the top. Logo bottom left please.") == "bottom_left"  # the user's ask wins
    assert al.suggest_corner("Headline across the top, CTA across the bottom.") == "top_right"  # nothing free: fall back


# ── the prompt the model sees ───────────────────────────────────────────────

LOCKED = (
    "Hero photo of a ring on velvet. Full-bleed photo; the Brand Kit logo is composited in a slim white header strip in post. "
    'Headline "Shine" top left. BRAND IDENTITY LOCK: the ONLY allowed brand name on this image is "Adoria Jewels". '
    'If any brand wordmark appears it must read exactly "Adoria Jewels" letter-for-letter (x). '
    "Collection names and nav labels must never appear as the store name."
)


def test_the_prompt_drops_the_white_strip_and_the_brand_lock_and_forbids_logos_and_names():
    prompt, corner = al.prepare_prompt(LOCKED, "auto", "Adoria Jewels")
    assert corner == "top_right"  # the headline uses the top left
    assert "white header strip" not in prompt and "BRAND IDENTITY LOCK" not in prompt
    assert "adoria" not in prompt.lower()
    assert "Hero photo of a ring on velvet" in prompt and 'Headline "Shine" top left' in prompt  # real content kept
    assert "top-right corner of the picture clear" in prompt
    assert prompt.endswith(still.NO_LOGO_SHORT)


def test_a_chosen_corner_is_used_as_is_and_none_asks_for_no_corner_room():
    chosen, corner = al.prepare_prompt("A shoe on a table.", "bottom_left", "Acme")
    assert corner == "bottom_left" and "bottom-left corner" in chosen and chosen.endswith(still.NO_LOGO_SHORT)
    nothing, corner = al.prepare_prompt("A shoe on a table.", "none", "Acme")
    assert corner == "" and "corner of the picture clear" not in nothing and nothing.endswith(still.NO_LOGO_SHORT)


def test_ordinary_words_that_appear_in_the_brand_name_are_kept():
    prompt, _ = al.prepare_prompt("Website traffic chart for a radius campaign", "auto", "Traffic Radius")
    assert "Website traffic chart for a radius campaign" in prompt


# ── placing the logo on the finished picture ────────────────────────────────


def test_auto_picks_a_clean_corner_and_avoids_corners_with_text(uploads):
    logo = _save(uploads, "logo.png", _logo())
    url = _ad(uploads, "a.png", busy=("top_right", "top_left", "bottom_right"))
    out = sl.place_logo_in_corner(image_url=url, corner="auto", tenant_id=TENANT, logo_url=logo)
    assert out["corner"] == "bottom_left" and out["auto"] is True and out["warnings"] == []
    assert _changed_corner(uploads, url, out["url"]) == "bottom_left"


def test_auto_prefers_the_suggested_corner_when_it_is_clean_and_top_right_otherwise(uploads):
    logo = _save(uploads, "logo.png", _logo())
    url = _ad(uploads, "b.png")
    assert sl.place_logo_in_corner(image_url=url, corner="auto", tenant_id=TENANT, logo_url=logo, suggested="bottom_left")["corner"] == "bottom_left"
    assert sl.place_logo_in_corner(image_url=url, corner="auto", tenant_id=TENANT, logo_url=logo)["corner"] == "top_right"


def test_auto_ignores_a_suggestion_that_turned_out_busy(uploads):
    logo = _save(uploads, "logo.png", _logo())
    url = _ad(uploads, "c.png", busy=("bottom_left",))
    out = sl.place_logo_in_corner(image_url=url, corner="auto", tenant_id=TENANT, logo_url=logo, suggested="bottom_left")
    assert out["corner"] != "bottom_left"


def test_auto_with_every_corner_busy_takes_a_clear_top_or_bottom_strip_instead(uploads):
    logo = _save(uploads, "logo.png", _logo())
    url = _ad(uploads, "d.png", busy=al.CORNERS)
    out = sl.place_logo_in_corner(image_url=url, corner="auto", tenant_id=TENANT, logo_url=logo)
    assert out["corner"] in {"top_center", "bottom_center"} and out["auto"] is True
    assert out["warnings"] == []  # a clear spot was found, so nothing to warn about


def test_a_user_chosen_corner_is_never_overridden_even_if_busy(uploads):
    logo = _save(uploads, "logo.png", _logo())
    url = _ad(uploads, "e.png", busy=("top_left",))
    out = sl.place_logo_in_corner(image_url=url, corner="top_left", tenant_id=TENANT, logo_url=logo)
    assert out["corner"] == "top_left" and out["auto"] is False and out["warnings"]


# ── finishing a job's image ─────────────────────────────────────────────────


def _finish(root, result, **kw):
    kw.setdefault("suggested", "")
    kw.setdefault("tenant_id", TENANT)
    kw.setdefault("logo_url", _save(root, "brandlogo.png", _logo()))
    kw.setdefault("logo_on_light_url", None)
    return asyncio.run(al.apply_mode(result, **kw))


def test_old_mode_and_non_dict_results_are_returned_untouched(uploads):
    url = _ad(uploads, "f.png")
    result = _result(url)
    assert _finish(uploads, result, mode="") is result
    assert _finish(uploads, "boom", mode="auto") == "boom"


def test_a_corner_choice_adds_the_logo_inside_the_picture_and_keeps_the_plain_copy(uploads):
    url = _ad(uploads, "g.png")
    out = _finish(uploads, _result(url), mode="bottom_right")
    assert out["logo_applied"] is True and out["logo_corner"] == "bottom_right" and out["logo_auto"] is False
    assert out["url"] != url and out["url_without_logo"] == url and out["logo_version"] == "light logo"
    assert _changed_corner(uploads, url, out["url"]) == "bottom_right"
    assert Image.open(_local(uploads, out["url"])).size == (W, H)  # no white strip, no resize


def test_auto_records_which_corner_it_chose(uploads):
    url = _ad(uploads, "h.png", busy=("top_right",))
    out = _finish(uploads, _result(url), mode="auto", suggested="top_right")
    assert out["logo_auto"] is True and out["logo_corner"] != "top_right"


def test_none_adds_no_logo_and_leaves_the_picture_alone(uploads):
    url = _ad(uploads, "i.png")
    out = _finish(uploads, _result(url), mode="none")
    assert out["url"] == url and out["logo_applied"] is False and out["logo_corner"] == "none"


def test_failed_images_and_remote_urls_are_not_touched(uploads):
    assert _finish(uploads, {"status": "failed", "url": None, "error": "x"}, mode="auto")["status"] == "failed"
    remote = _result("https://cdn.example.com/a.png")
    assert _finish(uploads, remote, mode="auto")["url"] == "https://cdn.example.com/a.png"


def test_a_missing_or_broken_logo_never_loses_the_picture(uploads):
    url = _ad(uploads, "j.png")
    no_logo = _finish(uploads, _result(url), mode="auto", logo_url=None)
    assert no_logo["url"] == url and no_logo["logo_applied"] is False and "No Brand Kit logo" in no_logo["warnings"][0]
    broken = _finish(uploads, _result(url), mode="auto", logo_url="/files/t/ads/missing.png")
    assert broken["url"] == url and broken["logo_applied"] is False and "could not be added" in broken["warnings"][0]


# ── Auto varies the spot per creative, like a designer ─────────────────────


def test_auto_gives_each_creative_its_own_spot_not_always_the_top_right():
    prompt = "A planter on a bench. Headline across the top."
    spots = [al.suggest_corner(prompt, seed="brief-1", index=i) for i in range(6)]
    assert len(set(spots)) >= 3
    assert all(s.startswith("bottom") for s in spots)  # the headline owns the top, so the logo never goes there
    assert [al.suggest_corner(prompt, seed="brief-1", index=i) for i in range(6)] == spots  # stable on regenerate


def test_a_top_centre_spot_is_only_offered_when_the_top_edge_has_no_text():
    free = {al.suggest_corner("A calm photo.", seed="s", index=i) for i in range(12)}
    assert "top_center" in free and "bottom_center" in free
    assert not {s for s in (al.suggest_corner("Headline in the top left.", seed="s", index=i) for i in range(12))} & {"top_left", "top_center"}


def test_the_prompt_reserves_the_spot_that_was_chosen_including_the_centre_strips():
    for mode in ("top_center", "bottom_center"):
        prompt, corner = al.prepare_prompt("A shoe.", mode, "Acme")
        assert corner == mode and "area of the picture clear" in prompt
    prompt, corner = al.prepare_prompt("A shoe.", "auto", "Acme", seed="b", index=2)
    assert corner in al.POSITIONS and corner.replace("_", "-") .split("-")[0] in prompt.lower().replace("-", " ").split() + ["top", "bottom"]


def test_every_picture_prompt_keeps_a_blank_band_along_the_top():
    for mode in ("auto", "bottom_right", "top_center", "none"):
        prompt, _ = al.prepare_prompt("A shoe on a table.", mode, "Acme")
        assert "slim blank band" in prompt and prompt.endswith(still.NO_LOGO_SHORT)
