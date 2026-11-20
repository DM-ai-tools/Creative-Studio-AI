"""Punchy, designed ads: hook hierarchy, highlighted payoff words, the hook's angle, and no invented people.

Born from a pasted designer brief that came out plain, with a man in it nobody asked for, because a hidden
"PROP BAN ... the person's expression" rule was appended to every pasted prompt (and it also banned the
red-circled cost and magnified callout the brief asked for).
"""

from pathlib import Path

import pytest
from PIL import Image

from app.services import ad_image_logo as al
from app.services import ad_image_punch as ap
from app.services import ad_image_text as at
from app.services import creative_studio_still as still
from app.services.icp_image_plan_service import _BAN_CIRCLED_PAPER_FIX

BRIEF = (
    'Creative 1: Are your keywords attracting the wrong customers? Main headline: "ARE YOU PAYING FOR CLICKS FROM PEOPLE '
    'WHO WILL NEVER BUY?" Supporting text: Your keyword strategy could be attracting the wrong audience. Offer: FREE '
    "30-MINUTE GOOGLE ADS AUDIT. CTA: FIND YOUR KEYWORD LEAKS. Designer instructions: Use a Google Ads Search Terms Report "
    "as the main background. Highlight three example search queries in red, amber and green. Make the headline the largest "
    "element. Use a bottom banner for the free audit."
)


def _font() -> Path:
    import matplotlib

    for path in (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ):
        if path.is_file():
            return path
    pytest.skip("no TrueType font available")


# ── the hidden rule that put a person in every pasted brief ─────────────────


def test_a_pasted_prompt_is_sent_exactly_as_written_with_nothing_hidden_added():
    from app.services.generation_job import _verbatim_slot_prompt

    out = _verbatim_slot_prompt(BRIEF, industry="Digital Marketing", niche="Google Ads")
    assert "PROP BAN" not in out and "person" not in out.lower() and "expression" not in out.lower()
    assert "highlighted amount" not in out  # the brief itself asks to highlight spend and add a callout
    assert out.startswith("Creative 1: Are your keywords")


def test_the_prop_ban_used_elsewhere_no_longer_asks_for_a_person():
    assert "person" not in _BAN_CIRCLED_PAPER_FIX.lower() and "expression" not in _BAN_CIRCLED_PAPER_FIX.lower()


def test_the_logo_guard_no_longer_forbids_software_screens_the_brief_asks_for():
    rule = still.NO_LOGO_SHORT
    assert "do not draw the advertiser's logo" in rule and "do not invent logos or brand names" in rule
    assert "no real company or product names" not in rule and "screens that the brief itself asks for are fine" in rule
    assert "Google" not in rule  # a generic rule, not one shaped around a client


# ── finding the headline and its payoff ─────────────────────────────────────


def test_the_main_headline_of_a_designer_brief_is_found():
    assert ap.extract_main_headline(BRIEF) == "ARE YOU PAYING FOR CLICKS FROM PEOPLE WHO WILL NEVER BUY?"
    assert ap.extract_main_headline('Headline: "Your ad budget is leaking"') == "Your ad budget is leaking"
    assert ap.extract_main_headline("A woman holding a ring") == ""


@pytest.mark.parametrize(
    "hook,phrase",
    [
        ("ARE YOU PAYING FOR CLICKS FROM PEOPLE WHO WILL NEVER BUY?", "NEVER BUY?"),
        ("Your ad budget leaking every click?", "every click?"),
        ("Supercharge Your Growth", "Growth"),
        ("Stop bleeding", ""),  # two words: nothing to single out
        ("Hello", ""),
        ("Real campaigns. Real Melbourne leads.", "Melbourne leads."),
        ("Your budget leaking **every click**?", "every click?"),  # the user's own marks win
        ("**Free** audit for local shops", "Free"),
    ],
)
def test_the_payoff_words_are_chosen_or_the_user_marks_them(hook, phrase):
    assert ap.highlight_phrase(hook) == phrase


def test_marked_words_lose_their_asterisks_and_punctuation_is_kept():
    assert ap.parse_marked("Your budget leaking **every click**?") == ("Your budget leaking every click?", {3, 4})
    assert ap.parse_marked("No marks here") == ("No marks here", set())
    assert ap.parse_marked("**All** of it") == ("All of it", {0})


# ── the art direction ───────────────────────────────────────────────────────


def test_the_art_direction_asks_for_a_big_hook_a_highlight_a_banner_and_a_loud_button():
    block = ap.punch_block(hook="ARE YOU PAYING FOR CLICKS FROM PEOPLE WHO WILL NEVER BUY?", accent="#A4D36B (green)", angle="pain_led")
    assert block.startswith("ART DIRECTION (where the brief above states a layout, follow it exactly")
    assert 'payoff words "NEVER BUY?"' in block and "Headline treatment for this creative:" in block
    assert "marker-style block in #A4D36B (green)" in block  # the default look when none is picked
    assert "largest element" in block and "full-width banner" in block and "large, high-contrast button" in block
    assert "Open on the pain in the viewer's own words" in block  # the hook's angle
    assert ap.punch_block(hook="", angle="")  # still gives a punchy direction with no hook known
    assert "highlighted" not in ap.punch_block(hook="Hi")


def test_every_ad_angle_the_app_offers_has_a_punch_line():
    from app.services.ad_angle_library import AD_ANGLE_CATALOG

    assert {angle_id for angle_id, *_ in AD_ANGLE_CATALOG} <= set(ap.ANGLE_PUNCH)


def test_people_are_only_allowed_when_the_prompt_asks_for_one():
    assert not ap.mentions_person(BRIEF)  # "PEOPLE" in the quoted headline and "customers" are not a person in the picture
    assert ap.mentions_person("A stressed male business owner at a desk, hand on his temple")
    assert ap.mentions_person("Portrait of a smiling woman holding a ring")
    assert not ap.mentions_person('Headline "The man who never smiled"')  # inside quotes: just words
    no_people = ap.apply_punch(BRIEF, hook="X Y Z W")
    assert "Do not add people, faces or hands" in no_people
    with_person = ap.apply_punch("A smiling woman holds a ring. Headline text below.", hook="X Y Z W")
    assert "Do not add people" not in with_person


def test_the_art_direction_is_added_once_and_never_changes_the_users_words():
    once = ap.apply_punch(BRIEF, hook="ARE YOU PAYING FOR CLICKS FROM PEOPLE WHO WILL NEVER BUY?", angle="pain_led")
    assert once.startswith(BRIEF) and once.count("ART DIRECTION") == 1
    assert ap.apply_punch(once, hook="Something else") == once
    assert ap.apply_punch("", hook="x") == ""


def test_the_whole_pasted_brief_comes_out_clean_punchy_and_branded():
    from app.services import ad_image_brand as ab

    final = al.guard_prompt(BRIEF, "Traffic Radius")
    final = ap.apply_punch(final, hook=ap.extract_main_headline(BRIEF), accent=ab.accent_label("#A4D36B"), angle="pain_led")
    final = ab.apply_brand_style(final, primary="#A4D36B", secondary="#072032", font_heading="Arimo, 700", font_body="Arimo, 400")
    assert final.startswith(BRIEF) and "PROP BAN" not in final and "Traffic" not in final
    assert final.count("STRICT") == 1 and final.count("ART DIRECTION") == 1 and final.count("BRAND STYLE") == 1
    assert final.index("ART DIRECTION") < final.index("BRAND STYLE")  # the brand style comes last and wins
    assert "Headline in Arimo (a neutral Arial-style sans-serif)" in final


# ── the same punch when the app draws the text itself ───────────────────────


def _render(hook, **kw):
    font = _font()
    args = dict(headline="Stop the bleed", cta="Get Free Audit", primary="#A4D36B", secondary="#072032",
                heading_font=font, body_font=font, zone="bottom")
    args.update(kw)
    return at.render(Image.new("RGB", (800, 800), (20, 24, 40)), hook=hook, **args)


def test_the_payoff_words_sit_on_a_block_of_the_brand_colour():
    out, info = _render("Your ad budget leaking every click?")
    assert info["highlight"] == "every click?" and info["highlight_colour"] == "#A4D36B"
    assert info["hook_colour"] == "#FFFFFF"  # the rest of the hook is plain and readable
    green = sum(1 for p in out.getdata() if max(abs(a - b) for a, b in zip(p, (0xA4, 0xD3, 0x6B))) < 6)
    plain, _ = _render("Your ad budget leaking every click?", primary="")
    assert green > 1500 and green > sum(1 for p in plain.getdata() if max(abs(a - b) for a, b in zip(p, (0xA4, 0xD3, 0x6B))) < 6)


def test_the_user_can_mark_the_highlight_and_the_asterisks_are_never_printed():
    _, info = _render("Stop wasting **every single click** today")
    assert info["highlight"] == "every single click" and not any("*" in line for line in info["lines"])
    assert info["lines"][0].startswith("Stop wasting")


def test_a_two_word_hook_or_a_brand_with_no_colour_gets_no_highlight():
    assert _render("Stop bleeding")[1]["highlight"] == ""
    assert _render("Your ad budget leaking every click?", primary="", secondary="")[1]["highlight"] == ""


def test_each_creative_of_a_brief_gets_its_own_headline_treatment():
    from app.services import ad_image_punch as p

    hook = "Tired of watering your garden?"
    blocks = [p.apply_punch("Brief text.", hook=hook, accent="green", index=i, seed="brief-1") for i in range(6)]
    looks = {b.split("Headline treatment for this creative:")[1] for b in blocks}
    assert len(looks) == 6  # six creatives, six different looks
    assert all("where the brief above states a layout, follow it exactly" in b for b in blocks)
    assert all("picture must show what the headline claims" in b for b in blocks)
    # the same creative regenerated on its own keeps the same look
    one = p.apply_punch("Brief text.", hook=hook, accent="green", index=None, seed="img-9")
    assert one == p.apply_punch("Brief text.", hook=hook, accent="green", index=None, seed="img-9")
    # a different brief shuffles differently, and no treatment names an industry
    assert all(w not in " ".join(p.TREATMENTS).lower() for w in ("garden", "jewel", "dental", "plumb"))
