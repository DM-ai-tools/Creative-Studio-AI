import pytest

from app.services import ad_image_design as ad
from app.services import creative_studio_still as still

# The prompt a brief produced for a Traffic Radius static ad (the scene, then the layout and rule blocks
# the pipeline stacked on top of it).
REAL = (
    "Social proof credibility static ad. Bright modern digital marketing agency workspace, daytime. The PRIMARY HERO PROP: a "
    "large wall-mounted monitor or TV screen, clearly displaying a live Google Ads performance dashboard with upward-trending "
    "clicks and conversion columns, green positive percentage indicators. In the foreground, a confident Melbourne professional, "
    "female, late 20s, smart-casual, stands beside the screen holding a tablet, turning to face camera with a genuine open smile "
    "and relaxed shoulders, eyes lit with quiet pride. She is pointing lightly toward the screen results. SOCIAL PROOF CUES: behind "
    "her on the desk, a second laptop shows a Google Analytics-style traffic graph trending sharply upward; a branded Traffic Radius "
    "notepad sits next to it with handwritten campaign notes. The environment is unmistakably a digital marketing workspace, exposed "
    "concrete walls, neon-green accent strip light matching #A4D36B, a whiteboard in the background with 'PPC / Google Ads' written in "
    "marker. Lighting: warm-cool mix, professional but energised. Dark charcoal gradient lower-third overlay at bottom of frame. "
    "On-image text burned in: image_hook 'Real campaigns. Real Melbourne leads.' in bold white Kanit sans-serif Title Case. "
    "image_headline 'Google Ads management that delivers.' in white Montserrat subline. CTA pill: #A4D36B green background, white "
    "bold Montserrat 'Get Started Today'. Palette: #072032 deep navy in shadow areas, #A4D36B accent lighting. No fake logos or "
    "fabricated star ratings anywhere in frame. Shallow depth of field, 50mm portrait lens. BRAND IDENTITY LOCK: the ONLY allowed "
    'brand name on this image is "Traffic Radius". Do NOT render Traffic Radius, ClickTrends, or any agency/platform logo. '
    "Collection names and nav labels must never appear as the store name. TEXT-ANCHOR: TEXT on this image ONLY: upper-third "
    "'Real campaigns. Real Melbourne leads.' REQUIRED lower-third pill-shaped CTA button. PROP BAN (mandatory): do NOT include any "
    "paper, bill, invoice or phone screen with red/orange circles."
)


def _compose(index=0, **kw):
    args = dict(
        scene_source=REAL, seed="brief-1", index=index, hook="Real campaigns. Real Melbourne leads.",
        headline="Google Ads management that delivers.", cta="Get Started Today", primary="#A4D36B", secondary="#072032",
        font_heading="Kanit", font_body="Montserrat", brand_name="Traffic Radius",
    )
    args.update(kw)
    return ad.compose(**args)


def test_it_is_only_on_when_asked_for_and_the_campaign_left_styles_on_auto():
    on = {"image_design_variety": "varied"}
    assert ad.enabled(on, {}, "auto", "auto") and ad.enabled(on, {}, "", "") and ad.enabled({}, on, "auto", "auto")
    assert not ad.enabled({}, {}, "auto", "auto")  # existing briefs behave as before
    assert not ad.enabled({"image_design_variety": ""}, {}, "auto", "auto")
    assert not ad.enabled(on, {}, "jewellery_luxury", "auto")  # a style the user picked is respected
    assert not ad.enabled(on, {}, "auto", "flat_cartoon")


def test_a_batch_gets_a_different_design_per_image_until_the_library_runs_out():
    labels = [ad.style_for_variant(i, "brief-1")["label"] for i in range(len(ad.DESIGN_LIBRARY))]
    assert len(set(labels)) == len(ad.DESIGN_LIBRARY)
    assert ad.style_for_variant(0, "brief-1") == ad.style_for_variant(len(ad.DESIGN_LIBRARY), "brief-1")  # wraps round
    assert [ad.style_for_variant(i, "brief-1")["label"] for i in range(5)] != [ad.style_for_variant(i, "brief-2")["label"] for i in range(5)]
    assert ad.style_for_key("img-1") == ad.style_for_key("img-1")  # stable for one image


def test_the_scene_keeps_the_subject_and_drops_layout_type_and_brand_blocks():
    scene = ad.clean_scene(REAL)
    assert "confident Melbourne professional" in scene and "pointing lightly toward the screen" in scene
    for gone in ("lower-third", "gradient", "CTA", "Kanit", "Montserrat", "#A4D36B", "BRAND IDENTITY", "TEXT-ANCHOR", "image_hook"):
        assert gone not in scene
    assert len(scene) <= ad.MAX_SCENE_CHARS


def test_the_prompt_is_short_exact_about_the_words_and_carries_the_guardrails():
    prompt, label = _compose()
    assert len(prompt) < 1950 and len(prompt) < len(REAL) and label in {s["label"] for s in ad.DESIGN_LIBRARY}
    assert f"Design direction, {label}" in prompt
    for line in ('headline "Google Ads management that delivers."', 'supporting line "Real campaigns. Real Melbourne leads."', 'button reading "Get Started Today"'):
        assert line in prompt
    assert "primary #A4D36B" in prompt and "Headline in Kanit" in prompt
    assert "traffic radius" not in prompt.lower() and "BRAND IDENTITY LOCK" not in prompt
    assert prompt.endswith(still.NO_LOGO_SHORT) and "the company" not in prompt
    assert "lower-third" not in prompt and "pill" not in prompt  # the design decides layout, not the old template


def test_two_variants_of_one_brief_do_not_share_a_look():
    first, a = _compose(index=0)
    second, b = _compose(index=1)
    assert a != b and first != second
    assert first.split("Design direction")[1] != second.split("Design direction")[1]


def test_photo_only_and_no_cta_and_carousel_cards_are_handled():
    photo, _ = _compose(photo_only=True)
    assert "No text, letters or numbers anywhere on the image; a clean photo only." in photo and "button reading" not in photo
    assert "Kanit" not in photo and "Typography" not in photo and "Type style" not in photo  # no type on the image
    middle_card, _ = _compose(cta="", frame_note="Card 2 of 4 in one swipe story; ONE square 1:1 card only.")
    assert "No button or call-to-action" in middle_card and "button reading" not in middle_card and "Card 2 of 4" in middle_card
    nothing, _ = _compose(hook="", headline="", cta="")
    assert "No text, letters or numbers anywhere" in nothing


def test_a_thin_or_missing_scene_falls_back_and_never_produces_an_empty_prompt():
    prompt, _ = _compose(scene_source="", fallback_source=REAL)
    assert "confident Melbourne professional" in prompt
    bare, _ = _compose(scene_source="", fallback_source="")
    assert "Static social ad. A real, specific, well-lit scene" in bare


def test_quotes_in_copy_cannot_break_the_exact_text_line():
    prompt, _ = _compose(headline='Say "yes" to leads')
    assert "headline \"Say 'yes' to leads\"" in prompt


def test_screens_may_show_abstract_charts_but_never_readable_words():
    prompt, _ = _compose()
    assert "abstract shapes, charts and blocks of colour" in prompt and "keep those blank" not in prompt


def test_a_design_prompt_gets_the_corner_rule_without_repeating_the_guardrail():
    from app.services import ad_image_logo as al

    designed, _ = _compose()
    final, corner = al.prepare_prompt(designed, "bottom_left", "Traffic Radius")
    assert corner == "bottom_left" and "bottom-left corner" in final
    assert final.count("STRICT") == 1 and "traffic radius" not in final.lower()


def test_a_designer_brief_is_never_recomposed_or_captioned_by_the_app():
    from app.services import ad_image_design as d

    for source in ("strategy", "ai", "user", ""):
        slot = {"prompt": "Creative 1: x. Main headline: \"A\"", "prompt_source": source, "brief_complete": True}
        assert d.scene_may_be_redesigned(slot, True) is False
        assert d.scene_may_be_redesigned(slot, False) is False
    assert d.scene_may_be_redesigned({"prompt": "a scene", "prompt_source": "ai"}, True) is True
