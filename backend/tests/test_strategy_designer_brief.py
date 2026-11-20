"""A designer-style creative brief must be read by its structure: six "Creative N" sections are six images,
with every field exactly as written. (The AI parser turned this same file into twelve variants, read panels
and the arrows of a flow diagram as carousel cards, lost the headlines and copied one CTA onto the others.)"""

from pathlib import Path

import pytest

from app.api.v1.generation import StrategyVariantPlan
from app.services import strategy_parse_service as sps
from app.services.strategy_designer_brief import parse_designer_creatives

SAMPLE = (Path(__file__).parent / "fixtures" / "designer_brief_sample.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def variants():
    return parse_designer_creatives(SAMPLE, fallback_cta="LEARN MORE")


def test_six_creatives_become_six_images_in_order_with_their_own_numbers(variants):
    assert [v["id"] for v in variants] == ["C3", "C4", "C5", "C6", "C7", "C8"]
    assert {v["format"] for v in variants} == {"static"}  # panels and arrows never become carousel cards
    assert all(v["carousel_index"] is None for v in variants) if "carousel_index" in variants[0] else True


def test_every_headline_and_subheadline_is_exactly_as_written(variants):
    assert [v["hook"] for v in variants] == [
        "YOUR GARDEN, SMARTER FROM THE ROOTS",
        "FROM SMALL SPACES TO BIG GARDENS",
        "TIRED OF WATERING YOUR GARDEN?",
        "ONE GARDEN. YOUR WAY.",
        "EVERYTHING YOU NEED TO START GROWING",
        "GROW MORE. WATER LESS. DO LESS.",
    ]
    assert variants[0]["message"].startswith("WaterUps wicking technology helps deliver water from the reservoir")
    assert variants[4]["message"] == "Complete WaterUps Food Garden Packages"


def test_each_creative_keeps_its_own_cta_and_none_is_copied_from_another(variants):
    assert [v["cta"] for v in variants] == [
        "DISCOVER WATERUPS WICKING SYSTEMS",
        "FIND YOUR WATERUPS SOLUTION",
        "GROW SMARTER",
        "EXPLORE THE FULL RANGE",  # the note written under this CTA is not part of it
        "BUILD YOUR FOOD GARDEN",
        "EXPLORE FOOD GARDEN PACKAGES",
    ]


def test_the_visual_direction_is_kept_not_replaced_by_the_headline(variants):
    assert "cross-section illustration" in variants[0]["prompt"] and "Water reservoir at the bottom" in variants[0]["prompt"]
    assert "3-panel lifestyle composition" in variants[1]["prompt"] and "PANEL 2 – HOME GARDEN" in variants[1]["prompt"]
    assert "Split-screen design." in variants[2]["prompt"] and "TRADITIONAL WATERING" in variants[2]["prompt"]
    assert "product collage" in variants[3]["prompt"] and "Reservoir Level Indicator" in variants[3]["prompt"]
    assert "Display the different package sizes together" in variants[4]["prompt"]
    for v in variants:
        assert 'Main headline: "' + v["hook"] + '"' in v["prompt"]  # the headline is in the brief too


def test_a_flow_of_arrows_stays_one_line_inside_one_image(variants):
    assert "WATER RESERVOIR → WICKING SYSTEM → PLANT ROOTS → HEALTHIER GROWTH" in variants[0]["prompt"]
    assert "WATER RESERVOIR → WICKING TECHNOLOGY → CONSISTENT MOISTURE → HEALTHIER PLANTS" in variants[5]["prompt"]
    assert "flow diagram drawn inside this one image, not separate slides or cards" in variants[0]["prompt"]
    assert "flow diagram" not in variants[1]["prompt"]  # only creatives that have a flow say so
    assert "↓" not in "".join(v["prompt"] for v in variants)


def test_callouts_messages_and_small_text_are_carried_over(variants):
    assert "✓ Smarter water delivery ✓ Less frequent watering" in variants[0]["prompt"]
    assert "Message: ✓ Grow vegetables, herbs & flowers" in variants[1]["prompt"] or "✓ Grow vegetables, herbs & flowers" in variants[1]["prompt"]
    assert "Message: WATER WHERE YOUR PLANTS NEED IT." in variants[2]["prompt"]
    assert "Choose the package that fits your growing space." in variants[4]["prompt"]  # "Small supporting text"
    assert "Message: YOUR FOOD GARDEN, MADE SIMPLE." in variants[5]["prompt"]  # "Bottom Headline"
    assert variants[2]["prompt"].count("Creative 5: Stop Watering. Start Growing.") == 1  # no doubled full stop
    assert "Growing.." not in variants[2]["prompt"]


def test_the_brief_is_marked_complete_so_generate_ai_does_not_replace_it(variants):
    assert all(v["prompt_complete"] for v in variants)
    kept = sps._normalize_variant(variants[0], "LEARN MORE", "")
    assert kept["prompt_complete"] is True and kept["cta"] == "DISCOVER WATERUPS WICKING SYSTEMS"
    assert StrategyVariantPlan(**kept).prompt_complete is True
    assert StrategyVariantPlan().prompt_complete is False  # ordinary variants are unchanged


def test_the_creative_type_sets_the_hook_angle_when_it_is_clear(variants):
    assert [v["ad_angle"] for v in variants] == ["educational", "product_hero", "problem_agitate_solve", "product_hero", "", ""]
    from app.services.ad_angle_library import VALID_ANGLE_IDS

    assert {v["ad_angle"] for v in variants if v["ad_angle"]} <= VALID_ANGLE_IDS
    assert variants[0]["creative_type"] == "graphic"  # a cross-section illustration, not a photo


def test_files_in_other_shapes_are_left_to_the_other_parsers():
    assert parse_designer_creatives("") == [] and parse_designer_creatives("# Just a title\n\nSome notes.") == []
    carousel = "## Creative 1 – Offer\nMain headline: X\nCard 1: first\nCard 2: second\n"
    assert parse_designer_creatives(carousel) == []  # real cards belong to the carousel parser
    table = "|#|Format|Concept|\n|T1|Static|A woman holds a ring|\n"
    assert parse_designer_creatives(table) == []
    no_headline = "## Creative 1 – Idea\nVisual direction: a plain scene\nCTA: Go\n"
    assert parse_designer_creatives(no_headline) == []


def test_other_ways_of_writing_the_same_brief_are_understood():
    text = (
        'Creative 1: Are your keywords attracting the wrong customers?\n'
        'Pain point: Businesses may be paying for clicks that are not relevant.\n'
        'Main headline:\n"ARE YOU PAYING FOR CLICKS FROM PEOPLE WHO WILL NEVER BUY?"\n'
        "Supporting text:\nYour keyword strategy could be attracting the wrong audience.\nBroad match bringing irrelevant searches?\n"
        "Offer: FREE 30-MINUTE GOOGLE ADS AUDIT\nCTA: FIND YOUR KEYWORD LEAKS\n"
        "Designer instructions:\nUse a Search Terms Report as the main background.\n"
        "Additional visual direction for the designer:\nAdd a small magnified callout.\n"
    )
    (v,) = parse_designer_creatives(text, fallback_cta="")
    assert v["hook"] == "ARE YOU PAYING FOR CLICKS FROM PEOPLE WHO WILL NEVER BUY?"
    assert v["cta"] == "FIND YOUR KEYWORD LEAKS"
    for piece in ("Search Terms Report", "magnified callout", "FREE 30-MINUTE GOOGLE ADS AUDIT", "broad match bringing irrelevant searches".capitalize()):
        assert piece in v["prompt"], piece
    assert "Supporting text: Your keyword strategy could be attracting the wrong audience." in v["prompt"]
    assert "Pain point: Businesses may be paying for clicks that are not relevant." in v["prompt"]
    assert v["prompt"].startswith("Creative 1: Are your keywords attracting the wrong customers?")  # a question stays a question
    assert "customers?." not in v["prompt"] and "customers." not in v["prompt"].split("Main headline")[0]


def test_a_creative_with_no_cta_falls_back_to_the_campaign_cta():
    text = '## Creative 1 – T\n**MAIN HEADLINE:**\nBIG IDEA\n**VISUAL DIRECTION:**\nA calm scene.\n'
    assert parse_designer_creatives(text, fallback_cta="LEARN MORE")[0]["cta"] == "LEARN MORE"
    assert parse_designer_creatives(text, fallback_cta="")[0]["cta"] == ""


def test_the_parse_service_uses_it_and_reports_the_style():
    source = Path(sps.__file__).read_text(encoding="utf-8")
    assert "parse_designer_creatives(text, fallback_cta=cta)" in source
    assert '"designer_brief" if designer_doc' in source and "formats = [\"static\"]  # every \"Creative N\" section" in source
