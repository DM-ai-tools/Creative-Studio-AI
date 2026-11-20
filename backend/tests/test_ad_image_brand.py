"""The Brand Kit's colours and fonts must reach every ad image prompt (Adoria: gold #DBB45A, black,
Cormorant Garamond / Open Sans). They used to be skipped for AI-written, strategy-file and pasted prompts."""

import pytest

from app.services import ad_image_brand as ab
from app.services import ad_image_design as ad

GOLD, BLACK = "#DBB45A", "#000000"


def test_colours_get_a_plain_word_as_well_as_the_code():
    assert ab.describe_colour("#DBB45A") == "gold"
    assert ab.describe_colour("#000000") == "black"
    assert ab.describe_colour("#FFFFFF") == "white"
    assert ab.describe_colour("#A4D36B") == "green"
    assert ab.describe_colour("#072032") == "deep blue"
    assert ab.describe_colour("#7A1F33") == "deep red"
    assert ab.describe_colour("#FC602C") == "orange" and ab.describe_colour("#FF0000") == "red"  # the ClickTrends orange
    assert ab.describe_colour("#888888") == "grey"
    assert ab.describe_colour("nonsense") == ""
    assert ab.normalize_hex("dbb45a") == "#DBB45A" and ab.normalize_hex("#fc0") == "#FFCC00" and ab.normalize_hex("") == ""


def test_fonts_are_described_by_look_because_a_model_cannot_load_them_by_name():
    assert ab.describe_font("Cormorant Garamond") == "Cormorant Garamond (an elegant high-contrast display serif)"
    assert ab.describe_font("Open Sans") == "Open Sans (a clean humanist sans-serif)"
    assert ab.describe_font("open sans condensed").startswith("open sans condensed (a clean humanist")
    assert ab.describe_font("Acme Script") == "Acme Script (a script typeface)"
    assert ab.describe_font("Zorgle") == "Zorgle (match this typeface's style)"
    assert ab.describe_font("") == ""


def test_the_adoria_brand_style_line_states_colours_fonts_and_that_it_wins():
    line = ab.brand_style_line(GOLD, BLACK, "Cormorant Garamond", "Open Sans")
    assert line.startswith("BRAND STYLE (overrides any other colour or font named above)")
    assert "primary #DBB45A (gold)" in line and "secondary #000000 (black)" in line
    assert "Headline in Cormorant Garamond (an elegant high-contrast display serif)" in line
    assert "supporting text and button in Open Sans (a clean humanist sans-serif)" in line
    assert "used for the lettering, button and accents" in line and len(line) < 400


def test_photo_only_images_get_colours_but_no_type_instructions():
    line = ab.brand_style_line(GOLD, BLACK, "Cormorant Garamond", "Open Sans", photo_only=True)
    assert "#DBB45A" in line and "Cormorant" not in line and "Typography" not in line
    assert ab.brand_style_line("", "", "Cormorant Garamond", "", photo_only=True) == ""


def test_nothing_is_added_when_the_brand_has_neither_colours_nor_fonts():
    assert ab.brand_style_line("", "", "", "") == ""
    assert ab.apply_brand_style("A ring.", primary="", secondary="") == "A ring."


@pytest.mark.parametrize(
    "prompt",
    [
        "A pasted prompt: champagne-gold #D4AF37 serif headline, burgundy button, Montserrat body.",  # names its own palette
        "Boutique image.",  # the MD's one-line note
        "WITH-PERSON SHOT (mandatory): a woman at a laptop. PROP BAN (mandatory): no circled paper.",  # an AI/pipeline prompt
    ],
)
def test_every_kind_of_prompt_ends_with_the_brand_style_stated_once(prompt):
    out = ab.apply_brand_style(prompt, primary=GOLD, secondary=BLACK, font_heading="Cormorant Garamond", font_body="Open Sans")
    assert out.startswith(prompt) and out.count("BRAND STYLE") == 1
    assert out.rstrip().endswith("Letter it in these typeface styles.")  # last, where it weighs most
    assert ab.apply_brand_style(out, primary="#FF0000", secondary="#00FF00") == out  # calling it again changes nothing


def test_a_designed_prompt_carries_the_same_line_and_is_not_given_a_second_one():
    prompt, _ = ad.compose(
        scene_source="A woman rests her hand on a table, ring on her finger, warm natural light and a calm mood.",
        seed="adoria", index=0, hook="The one she'll wear every day", headline="Make it perfect", cta="Book a Consultation",
        primary=GOLD, secondary=BLACK, font_heading="Cormorant Garamond", font_body="Open Sans",
    )
    assert prompt.count("BRAND STYLE") == 1 and "(an elegant high-contrast display serif)" in prompt
    again = ab.apply_brand_style(prompt, primary="#FF0000", font_heading="Kanit")
    assert again == prompt.rstrip() and "#FF0000" not in again


def test_the_job_uses_the_saved_brand_kit_colours_not_a_social_feed_override():
    import inspect

    from app.services import generation_job as job

    source = inspect.getsource(job)
    assert source.count('str(snap.get("primary_color") or') >= 4  # both prompt paths, both brand-style calls
    assert "_ad_brand.apply_brand_style(" in source
