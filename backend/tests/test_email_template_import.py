"""Customer-supplied email HTML: find image spots, swap only their addresses."""

import io

import pytest
from PIL import Image

from app.services.email_template_image_service import (
    aspect_format_type,
    build_slot_prompt,
    crop_to_target,
)
from app.services.email_template_import_service import (
    analyze_email_html,
    apply_image_replacements,
)

SAMPLE = """<!DOCTYPE html>
<html><head><title>Sale</title>
<style>.hero{background-image:url('https://cdn.example.com/hero.jpg')}</style>
</head>
<body bgcolor="#ffffff">
<!--[if mso]><v:rect><v:fill type="frame" src="https://cdn.example.com/hero.jpg" /></v:rect><![endif]-->
<table width="600" align="center"><tr><td>
  <img src="https://cdn.example.com/logo.png" alt="Acme logo" width="160" height="40" style="display:block">
</td></tr>
<tr><td background="https://cdn.example.com/hero.jpg" width="600" height="300">
  <img src="https://cdn.example.com/hero.jpg?a=1&amp;b=2" alt="Summer sale" width="600" height="300">
</td></tr>
<tr><td><h1>Hi {{first_name}}, big savings</h1>
  <img src="https://cdn.example.com/product.jpg" alt="Boots" width="280" height="280">
  <img src='https://cdn.example.com/photo.jpg' width=600>
  <a href="{{unsubscribe_url}}"><img src="https://cdn.example.com/facebook.png" width="32" height="32" alt="Facebook"></a>
  <img src="https://track.example.com/open.gif?id=1" width="1" height="1" alt="">
</td></tr></table>
<div style="width:600px;height:200px;background:#eee url(https://cdn.example.com/band.jpg) no-repeat">Offer</div>
</body></html>"""


def _by_src(analysis, fragment):
    return [s for s in analysis["slots"] if fragment in s["src"]]


def test_finds_every_image_spot_in_order():
    a = analyze_email_html(SAMPLE)
    srcs = [s["src"] for s in a["slots"]]
    assert srcs == [
        "https://cdn.example.com/logo.png",
        "https://cdn.example.com/hero.jpg",  # td background attribute
        "https://cdn.example.com/hero.jpg?a=1&b=2",  # entity decoded for display
        "https://cdn.example.com/product.jpg",
        "https://cdn.example.com/photo.jpg",
        "https://cdn.example.com/facebook.png",
        "https://track.example.com/open.gif?id=1",
        "https://cdn.example.com/band.jpg",  # inline style background
    ]
    assert [s["id"] for s in a["slots"]] == [f"s{i}" for i in range(1, 9)]


def test_roles_and_default_choice():
    a = analyze_email_html(SAMPLE)
    logo = _by_src(a, "logo.png")[0]
    assert logo["role"] == "logo" and not logo["replaceable"]
    assert _by_src(a, "facebook")[0]["role"] == "icon" and not _by_src(a, "facebook")[0]["replaceable"]
    track = _by_src(a, "open.gif")[0]
    assert track["role"] == "tracking" and not track["replaceable"]
    hero = _by_src(a, "hero.jpg?a=1")[0]
    assert hero["replaceable"] and hero["role"] in {"hero", "banner"}
    product = _by_src(a, "product.jpg")[0]
    assert product["replaceable"] and product["role"] == "product"
    assert a["replaceable_count"] == sum(1 for s in a["slots"] if s["replaceable"])


def test_sizes_come_from_attributes_and_styles():
    a = analyze_email_html(SAMPLE)
    hero = _by_src(a, "hero.jpg?a=1")[0]
    assert (hero["display_width"], hero["display_height"]) == (600, 300)
    assert (hero["plan_width"], hero["plan_height"]) == (600, 300)
    assert hero["size_assumed"] is False
    band = _by_src(a, "band.jpg")[0]
    assert (band["display_width"], band["display_height"]) == (600, 200)
    # Only a width is known: the height is planned as 3:2 and flagged as assumed.
    photo = _by_src(a, "photo.jpg")[0]
    assert photo["display_width"] == 600 and photo["display_height"] is None
    assert (photo["plan_width"], photo["plan_height"]) == (600, 400)
    assert photo["size_assumed"] is True


def test_merge_tags_are_reported():
    a = analyze_email_html(SAMPLE)
    assert "{{first_name}}" in a["merge_tags"] and "{{unsubscribe_url}}" in a["merge_tags"]


def test_context_text_is_the_nearest_preceding_text():
    a = analyze_email_html(SAMPLE)
    assert "big savings" in _by_src(a, "product.jpg")[0]["context_text"]


def test_export_changes_only_the_chosen_addresses():
    a = analyze_email_html(SAMPLE)
    product_id = _by_src(a, "product.jpg")[0]["id"]
    result = apply_image_replacements(SAMPLE, {product_id: "https://img.example.org/new.jpg"})
    out = result["html"]
    assert result["applied"] == [product_id]
    assert out == SAMPLE.replace("https://cdn.example.com/product.jpg", "https://img.example.org/new.jpg")
    # Every untouched piece survives exactly.
    assert "{{first_name}}" in out and "{{unsubscribe_url}}" in out
    assert "<!--[if mso]><v:rect>" in out


def test_export_roundtrip_with_nothing_chosen_is_identical():
    assert apply_image_replacements(SAMPLE, {})["html"] == SAMPLE


def test_export_replaces_every_use_of_a_repeated_picture():
    a = analyze_email_html(SAMPLE)
    hero_slots = [s["id"] for s in a["slots"] if s["src"] == "https://cdn.example.com/hero.jpg"]
    new = "https://img.example.org/h.jpg"
    out = apply_image_replacements(SAMPLE, {hero_slots[0]: new})["html"]
    # The td background was replaced; the Outlook VML copy and the <style> copy share that
    # address, and no other spot uses it, so they follow.
    assert "https://cdn.example.com/hero.jpg'" not in out and 'src="https://cdn.example.com/hero.jpg"' not in out
    assert out.count(new) == 3


def test_shared_address_is_not_touched_when_only_some_spots_change():
    html = '<img src="https://x.com/a.jpg" width="300" height="300"><img src="https://x.com/a.jpg" width="300" height="300">'
    out = apply_image_replacements(html, {"s1": "https://y.com/n.jpg"})["html"]
    assert out == '<img src="https://y.com/n.jpg" width="300" height="300"><img src="https://x.com/a.jpg" width="300" height="300">'


def test_ampersands_are_escaped_and_unknown_or_bad_urls_are_skipped():
    html = '<img src="https://x.com/a.jpg" width="300" height="300">'
    ok = apply_image_replacements(html, {"s1": "https://y.com/n.jpg?a=1&b=2"})
    assert 'src="https://y.com/n.jpg?a=1&amp;b=2"' in ok["html"]
    bad = apply_image_replacements(html, {"s1": "javascript:alert(1)", "s9": "https://y.com/z.jpg"})
    assert bad["html"] == html
    assert {s["id"] for s in bad["skipped"]} == {"s1", "s9"}


def test_localhost_images_produce_a_warning():
    html = '<img src="https://x.com/a.jpg" width="300" height="300">'
    out = apply_image_replacements(html, {"s1": "http://localhost:3000/files/t/e/x.jpg"})
    assert out["warnings"]


def test_windows_line_endings_do_not_shift_positions():
    html = SAMPLE.replace("\n", "\r\n")
    a = analyze_email_html(html)
    product_id = _by_src(a, "product.jpg")[0]["id"]
    out = apply_image_replacements(html, {product_id: "https://img.example.org/new.jpg"})["html"]
    assert out == html.replace("https://cdn.example.com/product.jpg", "https://img.example.org/new.jpg")


def test_oversized_html_is_rejected():
    with pytest.raises(ValueError):
        analyze_email_html("<p>" + "x" * 400_001)


# ── image fitting ────────────────────────────────────────────────────────────


def _png(width, height, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize(
    "target,expected_ratio",
    [((600, 300), 2.0), ((300, 300), 1.0), ((200, 400), 0.5), ((600, 100), 6.0)],
)
def test_crop_matches_the_exact_shape_of_the_spot(target, expected_ratio):
    jpeg, (w, h) = crop_to_target(_png(1536, 1024), *target)
    image = Image.open(io.BytesIO(jpeg))
    assert image.format == "JPEG" and image.size == (w, h)
    assert abs(w / h - expected_ratio) < 0.02
    assert w <= 1600


def test_output_is_twice_the_display_width_for_sharp_screens():
    _, (w, _) = crop_to_target(_png(1536, 1024), 600, 300)
    assert w == 1200


def test_never_enlarges_beyond_the_pixels_available():
    _, (w, _) = crop_to_target(_png(500, 500), 600, 600)
    assert w == 500


def test_transparent_png_is_flattened_on_white():
    buf = io.BytesIO()
    Image.new("RGBA", (400, 400), (0, 0, 0, 0)).save(buf, format="PNG")
    jpeg, _ = crop_to_target(buf.getvalue(), 200, 200)
    pixel = Image.open(io.BytesIO(jpeg)).getpixel((10, 10))
    assert min(pixel) > 240


def test_absurd_target_sizes_are_rejected():
    with pytest.raises(ValueError):
        crop_to_target(_png(100, 100), 5, 5)


def test_model_shape_follows_the_target_shape():
    assert aspect_format_type(600, 300) == "video"
    assert aspect_format_type(300, 300) == "static"
    assert aspect_format_type(200, 400) == "reel"


def test_prompt_forbids_text_and_uses_the_description():
    prompt = build_slot_prompt(
        role="hero", width=600, height=300, description="a family hiking at sunrise", alt="",
        context_text="", brand_name="Acme", campaign_name="Summer sale", palette=("#111111", "#A3D16B"), notes="",
    )
    assert "a family hiking at sunrise" in prompt and "Acme" in prompt
    assert "no text" in prompt.lower() and "#A3D16B" in prompt


def test_wide_banner_prompt_asks_for_a_centred_panorama():
    prompt = build_slot_prompt(
        role="banner", width=600, height=100, description="", alt="Sale", context_text="",
        brand_name="Acme", campaign_name="", palette=None, notes="",
    )
    assert "panoramic" in prompt.lower()


def test_a_longer_address_that_starts_with_the_old_one_is_left_alone():
    html = (
        '<td background="https://x.com/a.jpg" width="600" height="300"></td>'
        '<img src="https://x.com/a.jpg?v=2" width="600" height="300">'
    )
    out = apply_image_replacements(html, {"s1": "https://y.com/n.jpg"})["html"]
    assert 'src="https://x.com/a.jpg?v=2"' in out  # untouched, not "https://y.com/n.jpg?v=2"
    assert 'background="https://y.com/n.jpg"' in out


# ── generate -> crop -> store, with the image model replaced by a stand-in ────


def test_generate_slot_image_crops_and_stores_a_public_file(tmp_path, monkeypatch):
    import asyncio

    from app.core.config import settings
    from app.services import email_template_image_service as svc
    from app.services.ai_service import AIService
    from app.services.file_service import file_service

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_service, "upload_dir", tmp_path)

    # The "model" drops a 3:2 PNG into the workspace and returns its /files/ address.
    folder = tmp_path / "tenant-1" / "generated"
    folder.mkdir(parents=True)
    (folder / "model.png").write_bytes(_png(1536, 1024))
    seen = {}

    async def fake_generate(self, **kwargs):
        seen.update(kwargs)
        return {"status": "done", "url": "/files/tenant-1/generated/model.png"}

    monkeypatch.setattr(AIService, "generate_image_asset", fake_generate)

    out = asyncio.run(
        svc.generate_slot_image(
            tenant_id="tenant-1", model="openai-gpt-image-2", role="hero", width=600, height=300,
            description="mountain sunrise", alt="", context_text="", brand_name="Acme",
            campaign_name="", palette=None, notes="",
        )
    )
    assert seen["format_type"] == "video" and "mountain sunrise" in seen["prompt"]
    assert out["url"].startswith("/files/tenant-1/email-images/") and out["url"].endswith(".jpg")
    stored = tmp_path / out["url"].removeprefix("/files/")
    image = Image.open(stored)
    assert image.size == (1200, 600) == (out["width"], out["height"])


def test_generate_slot_image_reports_provider_failures(monkeypatch):
    import asyncio

    from app.services import email_template_image_service as svc
    from app.services.ai_service import AIService

    async def failing(self, **kwargs):
        return {"status": "failed", "error": "content policy"}

    monkeypatch.setattr(AIService, "generate_image_asset", failing)
    with pytest.raises(RuntimeError, match="content policy"):
        asyncio.run(
            svc.generate_slot_image(
                tenant_id="t", model="m", role="hero", width=600, height=300, description="", alt="",
                context_text="", brand_name="", campaign_name="", palette=None, notes="",
            )
        )
