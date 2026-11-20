import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core.config import settings
from app.core.security import get_current_user
from app.services import creative_studio_still as still
from app.services import creative_studio_still_logo as sl

TENANT = "11111111-1111-1111-1111-111111111111"
GPT = "openai-gpt-image-2.6-sunburst"
W, H = 720, 1280


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    from app.services.file_service import file_service

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_service, "upload_dir", tmp_path)
    return tmp_path


def _save(root, name, image):
    folder = root / "t" / "brand"
    folder.mkdir(parents=True, exist_ok=True)
    image.save(folder / name)
    return f"/files/t/brand/{name}"


def _logo(colour):
    """A wide mark: coloured bar with a transparent border, so trimming has something to do."""
    img = Image.new("RGBA", (400, 160), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((40, 40, 359, 119), fill=colour)
    return img


def _picture(root, name, colour, busy_corner=None):
    img = Image.new("RGB", (W, H), colour)
    if busy_corner:
        draw = ImageDraw.Draw(img)
        x0 = 20 if busy_corner.endswith("left") else W - 220
        y0 = 20 if busy_corner.startswith("top") else H - 120
        for i in range(0, 200, 8):  # stripes, like text lines
            draw.rectangle((x0 + i, y0, x0 + i + 3, y0 + 100), fill=(255, 255, 255) if sum(colour) < 300 else (0, 0, 0))
    return _save(root, name, img)


def _brand(root):
    return _save(root, "logo_white.png", _logo((255, 255, 255, 255))), _save(root, "logo_dark.png", _logo((10, 20, 60, 255)))


def _local(root, url):
    return root / url.removeprefix("/files/")


def _changed_box(before, after):
    from PIL import ImageChops

    return ImageChops.difference(before.convert("RGB"), after.convert("RGB")).getbbox()


@pytest.mark.parametrize("corner", sl.CORNERS)
def test_logo_lands_inside_the_chosen_corner_and_nothing_else_changes(uploads, corner):
    white, dark = _brand(uploads)
    picture = _picture(uploads, "bg.png", (20, 24, 40))
    out = sl.place_logo_in_corner(image_url=picture, corner=corner, tenant_id=TENANT, logo_url=white, logo_on_light_url=dark)
    before, after = Image.open(_local(uploads, picture)), Image.open(_local(uploads, out["url"]))
    assert after.size == (W, H)
    left, top, right, bottom = _changed_box(before, after)
    assert (left < W / 2) == corner.endswith("left") and (top < H / 2) == corner.startswith("top")
    assert right - left <= W * sl.LOGO_WIDTH_RATIO + 2 and bottom - top <= H * sl.LOGO_MAX_HEIGHT_RATIO + 2
    assert left >= W * sl.MARGIN_RATIO - 2 and top >= 8 and right <= W and bottom <= H  # inside the edges
    assert out["corner"] == corner


def test_dark_picture_gets_the_light_logo_and_light_picture_gets_the_dark_logo(uploads):
    white, dark = _brand(uploads)
    night = sl.place_logo_in_corner(
        image_url=_picture(uploads, "night.png", (15, 15, 25)), corner="top_right", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark
    )
    day = sl.place_logo_in_corner(
        image_url=_picture(uploads, "day.png", (245, 245, 240)), corner="top_right", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark
    )
    assert (night["background"], night["logo_version"]) == ("dark", "light logo")
    assert (day["background"], day["logo_version"]) == ("light", "dark logo")

    def centre_pixel(result):
        img = Image.open(_local(uploads, result["url"])).convert("RGB")
        return img.getpixel((W - round(W * (sl.MARGIN_RATIO + sl.LOGO_WIDTH_RATIO / 2)), round(W * sl.MARGIN_RATIO) + 8))

    assert min(centre_pixel(night)) > 200  # white mark on the dark picture
    assert max(centre_pixel(day)) < 90  # navy mark on the light picture


def test_a_dark_only_logo_is_made_readable_on_a_dark_picture_and_keeps_its_colour(uploads):
    mark = Image.new("RGBA", (400, 160), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mark)
    draw.rectangle((40, 40, 120, 119), fill=(40, 200, 80, 255))  # green symbol
    draw.rectangle((140, 40, 359, 119), fill=(10, 20, 60, 255))  # dark wordmark
    only_dark = _save(uploads, "only_dark.png", mark)
    out = sl.place_logo_in_corner(
        image_url=_picture(uploads, "night2.png", (15, 15, 25)), corner="top_left", tenant_id=TENANT, logo_url=only_dark
    )
    after = Image.open(_local(uploads, out["url"])).convert("RGB")
    left, top, right, bottom = _changed_box(Image.new("RGB", (W, H), (15, 15, 25)), after)
    pixels = [after.getpixel((x, y)) for x in range(left, right) for y in range(top, bottom)]
    assert any(min(p) > 235 for p in pixels), "dark wordmark should turn white on a dark picture"
    assert any(p[1] > 150 and p[0] < 90 for p in pixels), "green symbol keeps its colour"
    word_x, word_y = left + round((right - left) * 0.66), (top + bottom) // 2  # middle of the wordmark block
    assert min(after.getpixel((word_x, word_y))) > 235, "the wordmark's body is white, not navy on near-black"


def test_brightness_is_judged_in_the_chosen_corner_not_the_whole_picture(uploads):
    white, dark = _brand(uploads)
    img = Image.new("RGB", (W, H), (15, 15, 25))
    ImageDraw.Draw(img).rectangle((0, H - 300, W, H), fill=(250, 250, 250))  # bright bottom, dark top
    url = _save(uploads, "split.png", img)
    top = sl.place_logo_in_corner(image_url=url, corner="top_left", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark)
    bottom = sl.place_logo_in_corner(image_url=url, corner="bottom_left", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark)
    assert top["background"] == "dark" and bottom["background"] == "light"


def test_a_corner_with_text_or_detail_is_reported_and_a_clear_one_is_not(uploads):
    white, dark = _brand(uploads)
    busy = sl.place_logo_in_corner(
        image_url=_picture(uploads, "busy.png", (15, 15, 25), busy_corner="top_left"), corner="top_left", tenant_id=TENANT, logo_url=white
    )
    clear = sl.place_logo_in_corner(
        image_url=_picture(uploads, "calm.png", (15, 15, 25), busy_corner="top_left"), corner="bottom_right", tenant_id=TENANT, logo_url=white
    )
    assert busy["warnings"] and "top-left" in busy["warnings"][0]
    assert clear["warnings"] == []


def test_the_original_picture_is_kept_and_a_new_file_is_saved(uploads):
    white, dark = _brand(uploads)
    picture = _picture(uploads, "keep.png", (15, 15, 25))
    before = _local(uploads, picture).read_bytes()
    out = sl.place_logo_in_corner(image_url=picture, corner="bottom_left", tenant_id=TENANT, logo_url=white)
    assert out["url"] != picture and _local(uploads, picture).read_bytes() == before


def test_single_logo_file_still_works_on_a_light_picture(uploads):
    white, _ = _brand(uploads)
    out = sl.place_logo_in_corner(image_url=_picture(uploads, "d2.png", (245, 245, 240)), corner="top_left", tenant_id=TENANT, logo_url=white)
    assert out["background"] == "light" and Image.open(_local(uploads, out["url"])).size == (W, H)


def test_clear_errors_for_a_bad_corner_a_missing_picture_and_a_missing_logo(uploads):
    white, _ = _brand(uploads)
    picture = _picture(uploads, "e.png", (15, 15, 25))
    with pytest.raises(ValueError, match="top-left"):
        sl.place_logo_in_corner(image_url=picture, corner="middle", tenant_id=TENANT, logo_url=white)
    with pytest.raises(ValueError, match="Choose a corner"):
        sl.place_logo_in_corner(image_url=picture, corner="none", tenant_id=TENANT, logo_url=white)
    with pytest.raises(ValueError, match="picture could not be found"):
        sl.place_logo_in_corner(image_url="/files/t/brand/nope.png", corner="top_left", tenant_id=TENANT, logo_url=white)
    with pytest.raises(ValueError, match="No usable brand logo"):
        sl.place_logo_in_corner(image_url=picture, corner="top_left", tenant_id=TENANT, logo_url=None)


def test_corner_names_are_forgiving_and_none_means_no_logo():
    assert sl.normalize_corner("Top-Right") == "top_right" and sl.normalize_corner("bottom left") == "bottom_left"
    assert sl.normalize_corner("") == sl.normalize_corner("none") == sl.normalize_corner(None) == ""
    assert sl.corner_prompt_rule("") == "" and sl.corner_prompt_rule(None) == ""


def test_the_picture_prompt_asks_for_an_empty_corner_and_no_drawn_logo(uploads, monkeypatch):
    from app.services import usage_tracker
    from app.services.media import registry

    seen = []

    class Provider:
        async def generate(self, **kw):
            seen.append(kw["prompt"])
            return {"status": "done", "url": "/files/t/generated/a.png", "provider": "openai", "model": GPT}

    monkeypatch.setattr(registry, "get_image_provider", lambda model=None: Provider())
    monkeypatch.setattr(usage_tracker, "record_media_generation", lambda **kw: None)
    monkeypatch.setattr(usage_tracker, "estimate_media_cost", lambda **kw: (0.04, 1.0))

    asyncio.run(still.generate_still(tenant_id=TENANT, prompt="A report screen", model=GPT, logo_corner="bottom_right"))
    asyncio.run(still.generate_still(tenant_id=TENANT, prompt="A report screen", model=GPT))
    assert "bottom-right corner" in seen[0] and "Do not draw any logo" in seen[0]
    assert "corner" not in seen[1]  # no corner requested, so no corner rule (the no-logo rule still applies)
    with pytest.raises(ValueError, match="top-left"):
        asyncio.run(still.generate_still(tenant_id=TENANT, prompt="x", model=GPT, logo_corner="diagonal"))


def test_logo_endpoint_places_the_logo_and_turns_errors_into_422(uploads):
    from app.api.v1 import generation

    white, dark = _brand(uploads)
    picture = _picture(uploads, "api.png", (15, 15, 25))
    app = FastAPI()
    app.include_router(generation.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": "u", "tenant_id": TENANT})()
    client = TestClient(app)
    ok = client.post(
        "/api/v1/generation/creative-studio/still-logo",
        json={"image_url": picture, "corner": "top_right", "logo_url": white, "logo_on_light_url": dark},
    )
    assert ok.status_code == 200 and ok.json()["logo_version"] == "light logo"
    bad = client.post("/api/v1/generation/creative-studio/still-logo", json={"image_url": picture, "corner": "diagonal", "logo_url": white})
    assert bad.status_code == 422 and "top-left" in bad.json()["detail"]


# ── strict guardrail: no drawn logo, no brand name, for every brand ─────────


@pytest.mark.parametrize(
    "brand,text",
    [
        ("Traffic Radius", "Dashboard with the Traffic Radius logo in the corner"),
        ("Traffic Radius", "A TrafficRadius report and trafficradius.com.au in the address bar"),
        ("Traffic Radius", "Traffic-Radius's monthly report header"),
        ("Acme", "Acme's invoice on the desk, ACME in bold at the top"),
        ("Café Noir & Co", "Menu board for Café Noir & Co"),
    ],
)
def test_the_brand_name_is_removed_in_every_form_it_can_be_written(brand, text):
    cleaned, removed = still.scrub_brand_name(text, brand)
    assert removed
    for needle in brand.replace("&", " ").lower().split():
        if len(needle) > 3 and needle not in {"noir", "caf"}:
            assert needle not in cleaned.lower().replace("-", "").replace(" ", "")
    assert "the company" not in cleaned  # nothing is left behind that the model could print instead
    assert "  " not in cleaned and not cleaned.startswith(" ") and " ," not in cleaned and " ." not in cleaned


def test_removing_the_name_leaves_clean_text_not_a_stand_in_phrase():
    cleaned, removed = still.scrub_brand_name('A branded Traffic Radius notepad. Footer "Traffic Radius", next to it.', "Traffic Radius")
    assert removed and cleaned == "A branded notepad. Footer, next to it."
    assert still.scrub_brand_name("Traffic Radius", "Traffic Radius") == ("", True)


def test_ordinary_words_and_other_text_are_left_alone():
    text = "A chart of website traffic by radius around the shop, with $412 spend"
    assert still.scrub_brand_name(text, "Traffic Radius") == (text, False)
    assert still.scrub_brand_name(text, "") == (text, False)
    assert still.scrub_brand_name(text, "  ") == (text, False)
    assert still.scrub_brand_name(text, None) == (text, False)
    assert still.scrub_brand_name("Acmeology lab and a macmeal", "Acme")[1] is False  # inside other words


def test_every_picture_prompt_carries_the_no_logo_rule_and_never_the_brand_name(uploads, monkeypatch):
    from app.services import usage_tracker
    from app.services.media import registry

    seen = []

    class Provider:
        async def generate(self, **kw):
            seen.append(kw["prompt"])
            return {"status": "done", "url": "/files/t/generated/a.png", "provider": "openai", "model": GPT}

    monkeypatch.setattr(registry, "get_image_provider", lambda model=None: Provider())
    monkeypatch.setattr(usage_tracker, "record_media_generation", lambda **kw: None)
    monkeypatch.setattr(usage_tracker, "estimate_media_cost", lambda **kw: (0.04, 1.0))

    for corner in (None, "top_right"):
        for brand in ("Traffic Radius", "", None):
            out = asyncio.run(
                still.generate_still(
                    tenant_id=TENANT, prompt="Report screen titled Traffic Radius Monthly with a table", model=GPT,
                    logo_corner=corner, brand_name=brand,
                )
            )
            sent = seen[-1]
            assert "do not draw any logo, brand mark, wordmark, company or brand name" in sent
            assert sent.endswith(still.NO_LOGO_RULE)  # the rule is last, where it weighs most
            if brand:
                assert "traffic radius" not in sent.lower()  # not even in the rule that forbids it
                assert "brand name was removed" in (out["note"] or "")
            else:
                assert "Traffic Radius" in sent and not out["note"]  # no active brand to protect: prompt untouched


# ── the logo is taken off its backdrop: no white box on the picture ─────────


def _boxed_logo():
    """A JPG-style logo: solid white backdrop, navy block with a white 'letter' hole, green symbol."""
    img = Image.new("RGBA", (400, 160), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((150, 40, 359, 119), fill=(10, 20, 60, 255))
    draw.rectangle((230, 60, 270, 100), fill=(255, 255, 255, 255))  # white letter inside the mark
    draw.rectangle((40, 40, 120, 119), fill=(40, 200, 80, 255))
    return img


def test_extract_removes_a_plain_backdrop_but_keeps_white_inside_the_mark():
    out = sl.extract_logo(_boxed_logo())
    assert out.getpixel((2, 2))[3] == 0 and out.getpixel((395, 155))[3] == 0  # backdrop gone
    assert out.getpixel((250, 80)) == (255, 255, 255, 255)  # the white letter is part of the logo
    assert out.getpixel((200, 50))[3] == 255 and out.getpixel((80, 80))[3] == 255
    assert out.getpixel((140, 80))[3] == 0  # the gap between symbol and wordmark is backdrop too


def test_extract_leaves_transparent_logos_non_plain_backdrops_and_all_white_marks_alone():
    transparent = _logo((10, 20, 60, 255))
    assert list(sl.extract_logo(transparent).getdata()) == list(transparent.getdata())
    photo = Image.linear_gradient("L").resize((100, 100)).convert("RGBA")  # corners differ: not a backdrop
    assert list(sl.extract_logo(photo).getdata()) == list(photo.getdata())
    all_white = Image.new("RGBA", (100, 50), (255, 255, 255, 255))
    assert sl.extract_logo(all_white).getpixel((50, 25))[3] == 255  # would leave nothing: kept as it was


def test_a_logo_with_a_white_backdrop_leaves_no_box_on_dark_or_light_pictures(uploads):
    boxed = _save(uploads, "boxed.png", _boxed_logo())
    for name, bg in (("night3.png", (15, 15, 25)), ("day3.png", (244, 244, 238))):
        picture = _picture(uploads, name, bg)
        out = sl.place_logo_in_corner(image_url=picture, corner="top_left", tenant_id=TENANT, logo_url=boxed)
        after = Image.open(_local(uploads, out["url"])).convert("RGB")
        left, top, right, bottom = _changed_box(Image.new("RGB", (W, H), bg), after)
        # a leftover box would make the changed area as wide as the whole 400x160 file (2.5:1);
        # the mark itself is 320x80 (4:1), and the gap between symbol and wordmark shows the picture
        assert 3.5 < (right - left) / (bottom - top) < 4.5, (name, (left, top, right, bottom))
        gap = (left + round((right - left) * 0.297), (top + bottom) // 2)
        assert max(abs(a - b) for a, b in zip(after.getpixel(gap), bg)) < 25, (name, after.getpixel(gap))
        assert out["background"] == ("dark" if sum(bg) < 300 else "light")


def test_a_chosen_corner_with_text_loses_the_logo_to_a_clear_corner_when_asked_to_avoid_text(uploads):
    white, dark = _brand(uploads)
    picture = _picture(uploads, "text_top_left.png", (15, 15, 25), busy_corner="top_left")
    kept = sl.place_logo_in_corner(image_url=picture, corner="top_left", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark)
    moved = sl.place_logo_in_corner(
        image_url=picture, corner="top_left", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark, avoid_text=True
    )
    assert kept["corner"] == "top_left"  # the manual endpoint still puts it exactly where it was told
    assert moved["corner"] != "top_left" and "was moved" in moved["warnings"][0]
    clear = _picture(uploads, "clear.png", (15, 15, 25))
    stays = sl.place_logo_in_corner(
        image_url=clear, corner="top_left", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark, avoid_text=True
    )
    assert stays["corner"] == "top_left" and stays["warnings"] == []


def test_the_logo_endpoint_puts_the_logo_exactly_where_the_user_clicked(uploads):
    from app.api.v1 import generation as gen

    source = open(gen.__file__, encoding="utf-8").read()
    body = source.split("creative_studio_still_logo(")[1].split("class CreativeStudioInsertItem")[0]
    assert "avoid_text=False" in body and "avoid_text=True" not in body


def test_a_logo_chosen_on_a_finished_image_is_never_moved_by_the_app():
    from app.api.v1 import variants
    from app.services import ad_image_logo

    source = open(variants.__file__, encoding="utf-8").read()
    body = source.split("async def place_variant_logo(")[1].split("async def regenerate_variant_image(")[0]
    assert "avoid_text=False" in body and "url_without_logo" in body  # always starts from the logo-free copy
    assert "avoid_text=True" not in open(ad_image_logo.__file__, encoding="utf-8").read()


@pytest.mark.parametrize("position", sl.CENTRE_POSITIONS)
def test_the_centre_positions_put_the_logo_in_the_middle_of_that_edge(uploads, position):
    white, dark = _brand(uploads)
    picture = _picture(uploads, "mid.png", (20, 24, 40))
    out = sl.place_logo_in_corner(image_url=picture, corner=position, tenant_id=TENANT, logo_url=white, logo_on_light_url=dark)
    before, after = Image.open(_local(uploads, picture)), Image.open(_local(uploads, out["url"]))
    left, top, right, bottom = _changed_box(before, after)
    assert abs((left + right) / 2 - W / 2) <= 3  # centred across the width
    if position == "top_center":
        assert top < H * 0.15
    elif position == "bottom_center":
        assert bottom > H * 0.85
    else:
        assert abs((top + bottom) / 2 - H / 2) <= 3
    assert out["corner"] == position
    assert sl.normalize_corner(position.replace("center", "centre").replace("_", "-")) == position  # 'top-centre' works


def test_every_corner_busy_lets_auto_use_a_clear_strip_along_the_top_or_bottom(uploads):
    white, dark = _brand(uploads)
    img = Image.new("RGB", (W, H), (15, 15, 25))
    draw = ImageDraw.Draw(img)
    for corner_x in (20, W - 220):
        for corner_y in (20, H - 120):
            for i in range(0, 200, 8):
                draw.rectangle((corner_x + i, corner_y, corner_x + i + 3, corner_y + 100), fill=(255, 255, 255))
    url = _save(uploads, "all_corners.png", img)
    out = sl.place_logo_in_corner(image_url=url, corner="auto", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark)
    assert out["corner"] in {"top_center", "bottom_center"} and out["auto"] is True


def test_a_white_plate_goes_behind_the_logo_and_the_busy_spot_no_longer_warns(uploads):
    white, dark = _brand(uploads)
    picture = _picture(uploads, "plate.png", (15, 15, 25), busy_corner="top_left")
    plain = sl.place_logo_in_corner(image_url=picture, corner="top_left", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark)
    plated = sl.place_logo_in_corner(image_url=picture, corner="top_left", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark, backing="plate")
    assert plain["warnings"] and plated["warnings"] == [] and plated["corner"] == "top_left"
    assert plated["url"] != plain["url"]


def test_a_logo_strip_adds_height_and_leaves_the_picture_untouched(uploads):
    from app.services.logo_overlay import file_url_to_local_path

    white, dark = _brand(uploads)
    picture = _picture(uploads, "strip.png", (15, 15, 25), busy_corner="bottom_right")
    before = Image.open(file_url_to_local_path(picture)).convert("RGB")
    out = sl.place_logo_in_corner(image_url=picture, corner="bottom_right", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark, backing="bar")
    after = Image.open(file_url_to_local_path(out["url"])).convert("RGB")
    assert after.width == before.width and after.height > before.height
    assert after.crop((0, 0, before.width, before.height)).tobytes() == before.tobytes()
    assert out["warnings"] == []


def test_a_busy_spot_gets_a_clear_band_not_a_logo_over_the_text_unless_asked(uploads):
    from app.services.logo_overlay import file_url_to_local_path

    white, dark = _brand(uploads)
    picture = _picture(uploads, "busytop.png", (15, 15, 25), busy_corner="top_left")
    before = Image.open(file_url_to_local_path(picture)).convert("RGB")
    smart = sl.place_logo_in_corner(image_url=picture, corner="top_left", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark)
    over = sl.place_logo_in_corner(image_url=picture, corner="top_left", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark, backing="over")
    smart_img = Image.open(file_url_to_local_path(smart["url"])).convert("RGB")
    over_img = Image.open(file_url_to_local_path(over["url"])).convert("RGB")
    assert smart["corner"] == "top_left" and "a little smaller" in smart["warnings"][0]
    assert smart_img.size == before.size  # still exactly the same shape and size
    # the top band is blank (one flat colour) where the logo is not, and the artwork moved down
    top_row = {smart_img.getpixel((x, 2)) for x in range(0, smart_img.width, 7)}
    assert len(top_row) <= 2
    assert over_img.size == before.size and over_img.tobytes() != smart_img.tobytes()


def test_a_clear_spot_is_used_as_is_with_no_strip(uploads):
    from app.services.logo_overlay import file_url_to_local_path

    white, dark = _brand(uploads)
    picture = _picture(uploads, "cleartop.png", (15, 15, 25))
    before = Image.open(file_url_to_local_path(picture))
    out = sl.place_logo_in_corner(image_url=picture, corner="top_right", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark)
    assert Image.open(file_url_to_local_path(out["url"])).size == before.size and out["warnings"] == []


def test_a_headline_running_into_the_top_edge_makes_the_picture_leave_room_for_the_logo(uploads):
    from app.services.logo_overlay import file_url_to_local_path

    white, dark = _brand(uploads)
    img = Image.new("RGB", (800, 800), (10, 90, 160))
    draw = ImageDraw.Draw(img)
    for i in range(0, 760, 12):  # a headline stuck to the top edge, like the WaterUps one
        draw.rectangle((20 + i, 0, 26 + i, 70), fill=(255, 255, 255))
    folder = uploads / "t" / "ads"
    folder.mkdir(parents=True, exist_ok=True)
    img.save(folder / "headline.png")
    out = sl.place_logo_in_corner(image_url="/files/t/ads/headline.png", corner="top_right", tenant_id=TENANT, logo_url=white, logo_on_light_url=dark)
    result = Image.open(file_url_to_local_path(out["url"])).convert("RGB")
    assert result.size == (800, 800) and out["corner"] == "top_right" and "a little smaller" in out["warnings"][0]
    assert result.getpixel((400, 2)) == result.getpixel((10, 2))  # the very top is clear of headline pixels
