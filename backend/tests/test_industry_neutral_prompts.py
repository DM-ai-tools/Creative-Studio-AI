"""Prompts that go to the image model must not carry another industry's or another client's names.

The "BRAND IDENTITY LOCK" was added to every prompt for every brand and listed jeweller names (Lusso, Tiffany,
Cartier) and the agency's own names (Traffic Radius, ClickTrends), even on a plumbing or digital-marketing ad.
"""

import re
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import icp_image_plan_service as icp

JEWELLER_AND_CLIENT_NAMES = ("lusso", "dimad", "she diamond", "tiffany", "cartier", "adoria", "traffic radius", "clicktrends")


def _lock(prompt, brand, industry="", niche=""):
    out = icp.enforce_brand_identity_in_prompt(prompt, brand_name=brand, industry=industry, niche=niche)
    return out[out.index("BRAND IDENTITY LOCK") :]


@pytest.mark.parametrize(
    "brand,industry,niche",
    [
        ("Acme Plumbing", "Plumbing", "Emergency plumber"),
        ("Bright Smiles", "Dental", "Teeth whitening"),
        ("Growth Co", "Digital Marketing", "Google Ads"),
        ("Fresh Eats", "Restaurant", "Catering"),
    ],
)
def test_the_brand_lock_of_a_non_jewellery_brand_names_no_jewellers_and_no_clients(brand, industry, niche):
    lock = _lock("A photo of the shop front.", brand, industry, niche).lower()
    for name in JEWELLER_AND_CLIENT_NAMES:
        assert name not in lock, name
    assert "jeweller" not in lock and "luxury" not in lock
    assert f'"{brand.lower()}"' in lock  # it still pins the real brand name
    assert "any other store or company name" in lock and "any other agency, platform or company logo" in lock


def test_a_jewellery_brief_still_gets_its_jeweller_line_but_with_no_client_names():
    lock = _lock("A ring on velvet.", "Stone & Co", "Jewellery", "Engagement rings").lower()
    assert "do not invent a jeweller or luxury-house name or copy a famous one" in lock
    for name in JEWELLER_AND_CLIENT_NAMES:
        assert name not in lock, name


def test_lookalike_jeweller_names_are_only_replaced_on_a_jewellery_brief():
    text = "An ad in the style of Lusso Diamonds."
    plain = icp.enforce_brand_identity_in_prompt(text, brand_name="Acme Plumbing", industry="Plumbing", niche="Plumber")
    assert "Lusso Diamonds" in plain.split("BRAND IDENTITY LOCK")[0]  # not a jewellery brief: left alone
    shop = icp.enforce_brand_identity_in_prompt(text, brand_name="Stone & Co", industry="Jewellery", niche="Engagement rings")
    assert "Lusso" not in shop.split("BRAND IDENTITY LOCK")[0] and "Stone & Co" in shop


def test_the_platform_names_come_from_a_setting_not_the_code(monkeypatch):
    assert "Traffic Radius" in settings.PLATFORM_BRAND_NAMES  # same default, so nothing changes until it is edited
    replaced = icp.enforce_brand_identity_in_prompt("Made by Traffic Radius and click trends.", brand_name="Acme", industry="Plumbing")
    assert "Traffic Radius" not in replaced.split("BRAND IDENTITY LOCK")[0] and "Acme" in replaced

    monkeypatch.setattr(settings, "PLATFORM_BRAND_NAMES", "Zenith Platform, Zen Labs")
    pattern = icp._platform_brand_regex()
    assert pattern.search("built on zenith  platform") and pattern.search("by ZEN LABS")
    assert not pattern.search("Traffic Radius")  # no longer special once it is not in the setting

    monkeypatch.setattr(settings, "PLATFORM_BRAND_NAMES", "")
    assert not icp._platform_brand_regex().search("Traffic Radius ClickTrends Zenith Platform")


def test_no_client_example_is_left_in_the_prompt_text_sent_for_every_brand():
    for module in ("icp_image_plan_service.py", "image_prompt_service.py"):
        source = (Path(icp.__file__).parent / module).read_text(encoding="utf-8")
        assert "Adoria" not in source, module
        assert "never invent Lusso" not in source and "Do NOT render Traffic Radius" not in source, module
        assert not re.search(r"e\.g\.\s+Adoria", source), module


# ── the keyword matcher: "ring " used to be found inside "catering", "flooring", "tutoring"... ──────────────

NOT_JEWELLERY = [
    ("Restaurant", "Catering"), ("Engineering", "Structural engineering"), ("Hearing clinic", "Hearing aids"),
    ("Education", "Tutoring"), ("Hairdresser", "Hair colouring"), ("Flooring", "Timber flooring"),
    ("Digital Marketing", "Google Ads"), ("Accounting", "Tax returns"), ("Real Estate", "Property management"),
    ("Gym", "Personal training"), ("Bakery", "Cakes"), ("Car dealer", "Used cars"), ("Cleaning", "Office cleaning"),
]


@pytest.mark.parametrize("industry,niche", NOT_JEWELLERY)
def test_ordinary_industries_are_not_mistaken_for_jewellery(industry, niche):
    assert icp._resolve_niche_category(niche=niche, industry=industry) != "jewellery"
    assert icp._is_jewellery_niche(niche=niche, industry=industry, text="A photo of the shop front.") is False


@pytest.mark.parametrize(
    "industry,niche",
    [
        ("Jewellery", "Engagement rings"), ("Fine jewellery", ""), ("Retail", "diamond ring"), ("", "ring"),
        ("Jeweller", "Wedding bands and rings"), ("Fashion accessories", "gold chain necklace"),
    ],
)
def test_real_jewellery_is_still_recognised(industry, niche):
    assert icp._is_jewellery_niche(niche=niche, industry=industry, text="") is True


@pytest.mark.parametrize(
    "industry,niche,category",
    [
        ("Plumbing", "Emergency plumber", "plumbing"),
        ("Roofing", "Roof restoration", "roofing"),
        ("Dental", "Root canal treatment", "root_canal"),
        ("Dental", "Teeth whitening", "whitening"),
        ("Landscaping", "Lawn care", "landscaping"),
        ("HVAC", "Air conditioning installation", "hvac"),
        ("Home improvement", "Home renovation", "home_improvement"),
    ],
)
def test_the_other_industries_the_table_knows_are_still_found(industry, niche, category):
    assert icp._resolve_niche_category(niche=niche, industry=industry) == category


def test_keywords_match_at_a_word_start_and_a_trailing_space_means_the_whole_word():
    assert icp._keyword_in("plumb", "emergency plumber") and icp._keyword_in("ring ", "a ring for her")
    assert not icp._keyword_in("ring ", "catering") and not icp._keyword_in("ring ", "flooring company")
    assert icp._keyword_in("ring ", "ring") and icp._keyword_in("rings", "wedding rings")
    assert not icp._keyword_in("roof", "waterproofing")  # inside a word, not at its start
    assert not icp._keyword_in("", "anything")
