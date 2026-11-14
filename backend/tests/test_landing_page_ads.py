import asyncio
import re

import pytest
from PIL import Image

from app.services.landing_page_ads_service import (
    _assert_public_https,
    _adaptive_logo_variant,
    _background_luminance,
    _set_job,
    create_landing_page_job,
    get_landing_page_job,
    _extract_html_brand_hints,
    _extract_page,
    _fallback_plan,
    _infer_brief,
    _plan_quality_error,
    _resolved_brand_name,
    _creative_assignments_for_job,
    _resolve_landing_ad_logo,
    _infer_audience_segments_from_evidence,
    _enrich_analysis_brand,
    _assign_palette_families,
    _brand_palette_prompt,
    _detect_australian_audience_context,
    _host_is_australia,
    _find_html_logo_url,
    _inspect_local_logo,
)


def test_brief_flags_australia_when_user_prompt_mentions_australia():
    brief = _infer_brief("Create 3 ads for Australian businesses on Meta.")
    assert brief.get("target_australian_audience") is True
    assert "Australian" in (brief.get("audience_localisation_hint") or "")


def test_audience_segments_inferred_from_landing_evidence():
    analysis = {
        "text": [
            "Free Google Ads audit for Australian small business owners",
            "Improve ROAS and qualified leads",
        ],
        "brand": {"facts": {"source_summary": "Clinic booking for patients in Melbourne"}},
    }
    segments = _infer_audience_segments_from_evidence(analysis)
    assert "marketing and growth leaders" in segments
    assert any("business" in s for s in segments)


def test_detect_australian_audience_from_com_au_host():
    au = _detect_australian_audience_context(
        {"final_url": "https://googleaudit.trafficradius.com.au/", "text": [], "evidence": []},
        "",
    )
    assert au["target_au"] is True
    assert _host_is_australia("https://example.com.au/path") is True


def test_prompt_resolves_carousel_count_ratio_and_no_humans():
    brief = _infer_brief("Create a 6-slide Meta carousel in 4:5. No people or presenters.")

    assert brief["format"] == "carousel"
    assert brief["asset_count"] == 6
    assert brief["ratio"] == "4:5"
    assert brief["width"] == 1080
    assert brief["height"] == 1350
    assert brief["no_humans"] is True


def test_prompt_accepts_arbitrary_explicit_dimensions():
    brief = _infer_brief("Create 3 ad variations at 1080x1320 for this product")

    assert brief["asset_count"] == 3
    assert brief["width"] == 1080
    assert brief["height"] == 1320
    assert brief["ratio"] == "9:11"


def test_google_display_prompt_infers_common_sizes():
    brief = _infer_brief("Create a Google Display ad set from this landing page")

    assert brief["platform"] == "google"
    assert brief["asset_count"] == 5
    assert brief["sizes"] == [
        {"width": 300, "height": 250},
        {"width": 336, "height": 280},
        {"width": 728, "height": 90},
        {"width": 300, "height": 600},
        {"width": 320, "height": 100},
    ]


def test_bulk_prompt_allows_fifteen_ads():
    brief = _infer_brief("Create 15 static ad variations at 1080x1350")

    assert brief["asset_count"] == 15
    assert len(brief["sizes"]) == 15
    assert all(size == {"width": 1080, "height": 1350} for size in brief["sizes"])


def test_landing_ad_logo_prefers_scraped_not_unrelated_brief_brand():
    class _Brand:
        name = "Traffic Radius"
        logo_url = "https://cdn.example/traffic-radius.png"

    scraped = _resolve_landing_ad_logo(
        "https://adoriajewels.com/shop",
        "https://adoriajewels.com/logo.png",
        _Brand(),
    )
    assert scraped == "https://adoriajewels.com/logo.png"

    wrong_brief_logo = _resolve_landing_ad_logo(
        "https://adoriajewels.com/shop",
        "https://cdn.example/traffic-radius.png",
        _Brand(),
    )
    assert wrong_brief_logo is None

    fallback = _resolve_landing_ad_logo(
        "https://googleaudit.trafficradius.com.au/",
        None,
        _Brand(),
    )
    assert fallback == "https://cdn.example/traffic-radius.png"


def test_html_brand_hints_read_theme_color_and_common_hexes():
    html = """
    <html><head>
    <meta name="theme-color" content="#112233">
    <style>.btn{background:#AABBCC;color:#112233}</style>
    </head><body></body></html>
    """
    hints = _extract_html_brand_hints(html)
    assert hints["primary_color"] == "#112233"
    assert hints["secondary_color"] in {"#AABBCC", "#112233"}
    assert "#AABBCC" in (hints.get("palette_hexes") or [])


def test_enrich_prefers_html_primary_when_firecrawl_clashes():
    html = """
    <html><head>
    <meta name="theme-color" content="#9ACD32">
    <style>.btn{background:#88C057;color:#12181B}</style>
    </head><body></body></html>
    """
    analysis: dict = {"final_url": "https://example.com/landing", "brand": {}}
    brand_context = {
        "provider": "firecrawl",
        "brand_name": "Example",
        "primary_color": "#0F1B3D",
        "secondary_color": "#00C2A8",
        "accent_color": "#00C2A8",
        "palette_hexes": ["#0F1B3D", "#00C2A8"],
        "logo_url": None,
    }
    _enrich_analysis_brand(analysis, brand_context=brand_context, html=html, brand_row=None)
    b = analysis["brand"]
    assert b["primary_color"] == "#9ACD32"
    assert "#9ACD32" in (b.get("palette_hexes") or [])
    _assign_palette_families(b)
    assert isinstance(b.get("palette_families"), list)


def test_brand_palette_prompt_locks_same_hue_family_across_slides():
    brand = {
        "palette_hexes": ["#9ACD32", "#A2D149", "#88C057", "#007BFF"],
        "primary_color": "#9ACD32",
        "secondary_color": "#007BFF",
        "accent_color": "#88C057",
        "background_color": "#F9FBF7",
        "color_scheme": "light",
    }
    _assign_palette_families(brand)
    p0 = _brand_palette_prompt(brand, slide_index=0, total_assets=3)
    p1 = _brand_palette_prompt(brand, slide_index=1, total_assets=3)
    assert "EXACT HEX LOCK" in p0 and "EXACT HEX LOCK" in p1
    assert "#9ACD32" in p0 and "#9ACD32" in p1
    lock_line = p0.split("EXACT HEX LOCK", 1)[1].split("\n", 1)[0]
    lock_hexes = re.findall(r"#[0-9A-Fa-f]{6}", lock_line)
    assert lock_hexes
    assert all(hex_code.upper() != "#007BFF" for hex_code in lock_hexes)


def test_creative_assignments_shuffle_three_distinct_styles():
    batch = _creative_assignments_for_job(3, 424242)
    styles = [row["style"] for row in batch]
    assert len(set(styles)) == 3
    assert styles != [
        "corkboard polaroid collage",
        "clean isometric 3D product scene",
        "dark cinematic conceptual 3D",
    ]


def test_different_job_seeds_change_style_order():
    a = [row["style"] for row in _creative_assignments_for_job(3, 111)]
    b = [row["style"] for row in _creative_assignments_for_job(3, 999_999)]
    assert a != b


def test_australian_people_assignments_require_relevant_human_scenes():
    batch = _creative_assignments_for_job(3, 424242, prefer_australian_people=True)

    assert len(batch) == 3
    assert sum(row["people_required"] is True for row in batch) == 1
    assert sum(row["people_required"] is False for row in batch) == 2
    assert any("Australian" in row["visual_approach"] for row in batch)
    assert any("campaign" in row["visual_approach"].lower() or "advertising" in row["visual_approach"].lower() for row in batch)
    assert len({row["style"] for row in batch}) == 3


def test_unrelated_selected_brand_cannot_leak_palette_into_landing_page():
    class _TrafficRadiusBrand:
        name = "Traffic Radius"
        primary_color = "#9ACD32"
        secondary_color = "#88C057"
        logo_url = "https://trafficradius.com.au/logo.png"

    html = """
    <html><head><meta name="theme-color" content="#F26A21">
    <style>.cta{background:#FF7A00;color:#1C2430}</style></head><body></body></html>
    """
    analysis = {
        "final_url": "https://goolgeaudit.clicktrends.com.au/",
        "brand": {},
    }
    context = {
        "provider": "firecrawl",
        "brand_name": "Clicktrends",
        "primary_color": "#F26A21",
        "secondary_color": "#1C2430",
        "palette_hexes": ["#F26A21", "#FF7A00", "#1C2430"],
        "logo_url": None,
    }

    _enrich_analysis_brand(
        analysis,
        brand_context=context,
        html=html,
        brand_row=_TrafficRadiusBrand(),
    )

    assert analysis["brand"]["primary_color"] == "#F26A21"
    assert "#9ACD32" not in analysis["brand"]["palette_hexes"]


def test_verified_logo_palette_overrides_page_builder_and_screenshot_colours():
    analysis = {"final_url": "https://goolgeaudit.clicktrends.com.au/", "brand": {}}
    context = {
        "provider": "firecrawl",
        "brand_name": "Clicktrends",
        "primary_color": "#188BF6",
        "secondary_color": "#565A7C",
        "accent_color": "#565A7C",
        "palette_hexes": ["#188BF6", "#0038FF", "#FF602F"],
        "logo_palette_hexes": ["#FF602F", "#F8A030"],
        "background_color": "#FFFFFF",
    }

    _enrich_analysis_brand(
        analysis,
        brand_context=context,
        html='<style>:root{--link:#188BF6;--brand:#FF602F;--ink:#222222}</style>',
        brand_row=None,
    )

    brand = analysis["brand"]
    assert brand["primary_color"] == "#FF602F"
    assert brand["secondary_color"] == "#222222"
    assert "#188BF6" not in brand["palette_hexes"]
    assert set(brand["palette_hexes"]).issubset({"#FF602F", "#F8A030", "#222222", "#FFFFFF", "#000000"})


def test_logo_inspection_rejects_tracking_pixel_and_samples_real_wordmark(monkeypatch, tmp_path):
    from app.services import landing_page_ads_service

    monkeypatch.setattr(landing_page_ads_service.settings, "UPLOAD_DIR", str(tmp_path))
    tenant = "tenant-logo-test"
    folder = tmp_path / tenant / "brand"
    folder.mkdir(parents=True)
    tiny = folder / "pixel.gif"
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(tiny, "GIF")
    logo = folder / "wordmark.png"
    Image.new("RGBA", (300, 90), (255, 96, 47, 255)).save(logo, "PNG")

    assert _inspect_local_logo(f"/files/{tenant}/brand/pixel.gif", tenant_id=tenant) == (False, [])
    usable, palette = _inspect_local_logo(f"/files/{tenant}/brand/wordmark.png", tenant_id=tenant)
    assert usable is True
    assert palette and palette[0].startswith("#F8")


def test_page_extraction_preserves_source_evidence_and_cta():
    analysis = _extract_page(
        "https://example.com/product",
        """
        <html><head><title>Example Product</title><meta name="description" content="A factual offer."></head>
        <body><h1>Organise your workspace</h1><p>Australian delivery available.</p>
        <a href="/buy">Shop now</a><img src="/product.png" alt="Modular storage cabinet"></body></html>
        """,
    )

    assert analysis["title"] == "Example Product"
    assert analysis["primary_cta"] == {"text": "Shop now", "url": "https://example.com/buy"}
    assert any(item["excerpt"] == "Australian delivery available." for item in analysis["evidence"])
    assert analysis["images"] == ["https://example.com/product.png"]
    assert analysis["image_candidates"] == [{
        "url": "https://example.com/product.png",
        "alt": "Modular storage cabinet",
        "width": "",
        "height": "",
    }]


def test_html_logo_fallback_finds_brand_wordmark_not_partner_badge():
    analysis = _extract_page(
        "https://goolgeaudit.clicktrends.com.au/",
        """
        <html><body>
        <img src="https://cdn.example.com/google-partner.png" class="partner-logo" alt="Google Partner">
        <img src="https://cdn.example.com/assets/clicktrends-white.svg" class="site-logo header-brand" alt="Clicktrends">
        </body></html>
        """,
    )

    assert _find_html_logo_url(analysis) == "https://cdn.example.com/assets/clicktrends-white.svg"


def test_fallback_plan_has_exact_requested_count_and_dimensions():
    brief = _infer_brief("Create a 4-slide 9:16 carousel without humans")
    analysis = {
        "title": "Example Product",
        "description": "A factual offer.",
        "primary_cta": {"text": "Shop now"},
        "evidence": [{"id": "dom_1", "excerpt": "A factual offer."}],
    }

    plan = _fallback_plan(analysis, brief)

    assert len(plan["slides"]) == 4
    assert [slide["index"] for slide in plan["slides"]] == [1, 2, 3, 4]
    assert all(slide["width"] == 1080 and slide["height"] == 1920 for slide in plan["slides"])
    assert all(slide["include_presenter"] is False for slide in plan["slides"])


def test_bulk_fallback_uses_distinct_landing_page_hooks_not_domain_name():
    brief = _infer_brief("Create 15 static ad variations at 1080x1350")
    evidence = [
        {"id": f"dom_{index}", "excerpt": text}
        for index, text in enumerate(
            [
                "Spending $5K+ on Google Ads but not getting enough qualified leads or sales?",
                "See where your advertising budget is leaking and what to fix first.",
                "Receive a free 30-minute account analysis.",
                "You are not seeing the return you want from Google Ads.",
                "High acquisition costs are cutting into profits.",
                "Google Ads audit and campaign review.",
                "Check whether your account is properly set up.",
                "Review conversion tracking and attribution.",
                "Prioritise campaign optimisation opportunities.",
                "Receive a practical 90-day action plan.",
                "The audit is free and carries no obligation.",
                "Take the recommendations in-house if you prefer.",
                "Trusted by growing Australian businesses.",
                "The audit takes under a minute to book.",
                "Claim your free Google Ads audit.",
            ],
            start=1,
        )
    ]
    analysis = {
        "title": "",
        "brand": {
            "name": "Traffic Radius",
            "facts": {"offers": ["Free 30-minute Google Ads audit"], "unique_selling_points": ["No obligation"]},
        },
        "primary_cta": {"text": "Get My Free Audit"},
        "evidence": evidence,
    }

    plan = _fallback_plan(analysis, brief)

    assert _plan_quality_error(plan, brief) is None
    assert len({slide["headline"].lower() for slide in plan["slides"]}) == 15
    assert len({slide["style"] for slide in plan["slides"]}) == 15
    assert len({slide["angle"] for slide in plan["slides"]}) == 15
    assert all(len(slide["creative_direction"].split()) >= 55 for slide in plan["slides"])
    assert all("trafficradius.com" not in slide["headline"].lower() for slide in plan["slides"])


def test_brand_name_is_recovered_from_scraped_source_summary():
    name = _resolved_brand_name(
        {"title": "", "final_url": "https://googleaudit.trafficradius.com.au/"},
        {
            "brand_name": "googleaudit.trafficradius.com.au",
            "brand_facts": {"source_summary": "Landing page. Positions Traffic Radius as a Google Premier Partner."},
        },
    )

    assert name == "Traffic Radius"


def test_public_url_validation_rejects_non_https_without_network_lookup():
    with pytest.raises(ValueError, match="HTTPS"):
        asyncio.run(_assert_public_https("http://example.com"))


def test_logo_lettering_adapts_to_background_but_brand_colour_is_preserved():
    logo = Image.new("RGBA", (2, 1))
    logo.putdata([(20, 20, 20, 255), (80, 190, 70, 255)])

    on_dark = _adaptive_logo_variant(logo, 25)

    assert on_dark.getpixel((0, 0)) == (255, 255, 255, 255)
    assert on_dark.getpixel((1, 0)) == (80, 190, 70, 255)

    white_logo = Image.new("RGBA", (2, 1))
    white_logo.putdata([(250, 250, 250, 255), (80, 190, 70, 255)])
    on_light = _adaptive_logo_variant(white_logo, 235)

    assert on_light.getpixel((0, 0)) == (18, 31, 42, 255)
    assert on_light.getpixel((1, 0)) == (80, 190, 70, 255)


def test_background_luminance_samples_logo_placement_area():
    image = Image.new("RGB", (10, 10), (245, 245, 245))
    image.paste((10, 10, 10), (0, 0, 5, 5))

    assert _background_luminance(image, (0, 0, 5, 5)) < 20
    assert _background_luminance(image, (5, 5, 10, 10)) > 240


def test_landing_page_run_is_a_persistent_session_with_one_brief_slot(monkeypatch, tmp_path):
    from app.services import landing_page_ads_service

    monkeypatch.setattr(landing_page_ads_service.settings, "UPLOAD_DIR", str(tmp_path))
    job = create_landing_page_job(
        tenant_id="tenant-session-test",
        user_id="user-session-test",
        payload={"landing_page_url": "https://example.com", "user_prompt": "Create one ad"},
    )

    assert job["brief_id"] is None
    assert job["created_at"]
    assert job["updated_at"]

    updated = _set_job(job["id"], brief_id="shared-brief-id", status="completed")
    restored = get_landing_page_job(job["id"], "tenant-session-test")

    assert updated["brief_id"] == "shared-brief-id"
    assert restored is not None
    assert restored["brief_id"] == "shared-brief-id"
    assert restored["updated_at"] >= restored["created_at"]
