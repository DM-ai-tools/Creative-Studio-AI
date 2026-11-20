"""The Adoria brief's three bugs: a logo asked for in the strategy file got drawn, the brand name
printed under a CTA, carousel cards came out in a different shape from static ads, and a scene
written by the strategy file or the AI was never given a designed look."""

import inspect

import pytest

from app.services import ad_image_design as ad
from app.services import ad_image_logo as al
from app.services import creative_studio_still as still
from app.services.media import openai_image_provider as oip

# What the strategy file's scene notes and the planner's prompt actually said.
MD_GRAPHIC = (
    "Clean, minimal graphic with 3 simple icons: 1. Book a free consultation. 2. Design with our jewellers. "
    "3. Wear it forever. Adoria logo bottom right. No product photography. Process-focused."
)
MD_GRAPHIC_2 = "Clean, minimal graphic. Large number prominently displayed. Adoria logo. Optional: 5-star Google review badge overlay."


# ── a logo or the brand's name must never be drawn ──────────────────────────


def test_a_logo_instruction_in_the_strategy_scene_is_dropped_not_obeyed():
    out = al.guard_body(MD_GRAPHIC, "Adoria Jewels")
    assert "logo" not in out.lower() and "adoria" not in out.lower()
    assert "3 simple icons" in out and "No product photography" in out  # the real scene stays
    assert "logo" not in al.guard_body(MD_GRAPHIC_2, "Adoria Jewels").lower()
    assert "5-star Google review badge overlay" in al.guard_body(MD_GRAPHIC_2, "Adoria Jewels")  # a different sentence: kept


def test_the_name_is_removed_as_the_brand_kit_has_it_and_as_people_shorten_it():
    for text in ("A shop sign saying Adoria Jewels", "A shop sign saying Adoria", "A shop sign saying ADORIA's"):
        out, removed = still.scrub_brand_name(text, "Adoria Jewels")
        assert removed and "adoria" not in out.lower(), (text, out)
    # a name with no generic ending is only matched whole, and ordinary words survive
    assert still.scrub_brand_name("website traffic", "Traffic Radius") == ("website traffic", False)
    # a short alias would hit ordinary words, so it is not used
    assert still.scrub_brand_name("a blue sky", "Blue Group") == ("a blue sky", False)
    assert still.scrub_brand_name("Acme", "Acme Co")[1] is False


def test_the_brand_lock_the_pipeline_adds_is_removed():
    locked = (
        "A ring on velvet. BRAND IDENTITY LOCK: the ONLY allowed brand name on this image is \"Adoria Jewels\". "
        "If any brand wordmark appears it must read exactly \"Adoria Jewels\". "
        "Collection names and nav labels must never appear as the store name."
    )
    out = al.guard_body(locked, "Adoria Jewels")
    assert out == "A ring on velvet." and "BRAND IDENTITY" not in out


def test_the_guard_is_added_once_in_every_mode_including_the_old_white_strip_mode():
    legacy = al.guard_prompt("A woman holding a ring. Brand logo top left.", "Adoria Jewels")
    assert legacy.endswith(still.NO_LOGO_SHORT) and "A woman holding a ring." in legacy
    assert legacy.count("STRICT") == 1 and "Brand logo top left" not in legacy
    again = al.guard_prompt(legacy, "Adoria Jewels")  # running it twice changes nothing
    assert again == legacy
    corner, hint = al.prepare_prompt(MD_GRAPHIC, "auto", "Adoria Jewels")
    assert hint == "bottom_right"  # the corner the strategy file asked for is still honoured, by placing the real logo
    assert "Adoria" not in corner and corner.count("STRICT") == 1 and "bottom-right corner" in corner


# ── the scene is built on, not replaced by a one-liner ──────────────────────


def test_only_hand_written_prompts_are_left_exactly_as_written():
    redo = ad.scene_may_be_redesigned
    assert redo({}, verbatim_slot=False)  # no prompt at all
    assert redo({"prompt_source": "strategy"}, verbatim_slot=True)
    assert redo({"prompt_source": "ai"}, verbatim_slot=True)
    assert not redo({"prompt_source": "user"}, verbatim_slot=True)
    assert not redo({}, verbatim_slot=True)  # older brief, source unknown: treated as written by a person
    assert not redo(None, verbatim_slot=True)


def test_people_are_cast_for_the_stated_audience_and_place():
    audience = {"audience_type": "Women", "age_range": "25–35", "geography": "Melbourne VIC", "languages": "English"}
    prompt, _ = ad.compose(
        scene_source="A woman rests her hand on a table, ring on her finger, warm natural light and a calm mood.",
        seed="b", index=0, hook="The one she'll wear every day", cta="Book a Consultation", audience=audience,
    )
    assert "cast them naturally for Women 25–35 in Melbourne VIC" in prompt
    assert "no culturally specific costume, accessories or setting" in prompt
    none, _ = ad.compose(scene_source="A woman rests her hand on a table in warm light, calm.", seed="b", index=0, audience=None)
    assert "cast them" not in none


def test_a_strategy_scene_with_a_logo_ask_still_builds_a_clean_designed_prompt():
    prompt, label = ad.compose(
        scene_source=MD_GRAPHIC, seed="adoria", index=2, hook="Book Your Free Jewellery Consultation",
        headline="3 steps to your dream ring", cta="Book a Consultation", brand_name="Adoria Jewels",
    )
    assert "logo" not in prompt.replace(still.NO_LOGO_SHORT, "").lower() and "adoria" not in prompt.lower()
    assert label in prompt and 'headline "3 steps to your dream ring"' in prompt


# ── every ad image is the same shape as the one the user chose ──────────────


@pytest.mark.parametrize(
    "fmt,aspect,expected",
    [
        ("static", "1:1", "1024x1024"),
        ("carousel", "1:1", "1024x1024"),  # was 1536x1024: the carousel cards looked wider than the statics
        ("static", "4:5", "1024x1536"),
        ("carousel", "16:9", "1536x1024"),
        ("static", "1200x628", "1536x1024"),
        ("reel", "1:1", "1024x1536"),  # reels and videos keep their own shape
        ("video", "1:1", "1536x1024"),
    ],
)
def test_the_chosen_ratio_decides_the_image_size(fmt, aspect, expected):
    assert oip._size_for("gpt-image-1", fmt, aspect) == expected


def test_callers_that_pass_no_ratio_get_exactly_what_they_got_before():
    assert oip._size_for("gpt-image-1", "carousel") == "1536x1024"  # Creative Studio's 4:3 relies on this
    assert oip._size_for("gpt-image-1", "static") == "1024x1024"
    assert oip._size_for("dall-e-3", "carousel") == "1792x1024"
    assert oip._size_for("gpt-image-1", "static", "nonsense") == "1024x1024"


def test_seedream_follows_the_ratio_too():
    from app.services.media.byteplus_seedream_client import map_format_to_size

    assert map_format_to_size("carousel", "1:1") == "1024x1024" and map_format_to_size("static", "1:1") == "1024x1024"


def test_only_providers_that_can_use_a_ratio_are_given_one():
    from app.services.media.byteplus_seedream_provider import BytePlusSeedreamProvider

    for provider in (oip.OpenAIImageProvider, BytePlusSeedreamProvider):
        assert "aspect_ratio" in inspect.signature(provider.generate).parameters

    import asyncio

    from app.services import ai_service as svc

    seen = {}

    class WithRatio:
        async def generate(self, *, prompt, tenant_id, model, format_type, logo_url=None, logo_on_light_url=None,
                           reference_image_url=None, aspect_ratio=None):
            seen["with"] = aspect_ratio
            return {"status": "done", "url": "/files/x.png"}

    class WithoutRatio:
        async def generate(self, *, prompt, tenant_id, model, format_type, logo_url=None, logo_on_light_url=None,
                           reference_image_url=None):
            seen["without"] = "called"
            return {"status": "done", "url": "/files/x.png"}

    for cls in (WithRatio, WithoutRatio):
        svc.get_image_provider = lambda model, _c=cls: _c()
        asyncio.run(svc.AIService().generate_image_asset(prompt="p", tenant_id="t", model="m", format_type="carousel", aspect_ratio="1:1"))
    assert seen == {"with": "1:1", "without": "called"}


# ── a variant with no MD file: short typed prompts are scenes, complete ones are respected ──

PASTED_COMPLETE = (
    "Premium static ad, 1:1. A smiling woman in a bright Melbourne boutique holds an engagement ring toward the camera. "
    "TEXT ON IMAGE ONLY: headline 'Make it perfect' in champagne-gold serif at top left, CTA pill 'Book a Consultation' "
    "bottom centre. Lighting: soft daylight. Palette: gold and black. Shallow depth of field, 50mm lens."
)


@pytest.mark.parametrize(
    "typed",
    [
        "woman holding a ring in a boutique",
        "A couple choosing a diamond with a jeweller, bright airy room, natural light.",
        "close-up of a hand with an engagement ring",
        "ring",
    ],
)
def test_a_short_typed_prompt_is_a_scene_to_build_on(typed):
    assert ad.is_short_scene(typed)
    assert ad.scene_may_be_redesigned({"prompt": typed, "prompt_source": "user"}, verbatim_slot=True)
    assert ad.scene_may_be_redesigned({"prompt": typed}, verbatim_slot=True)  # older brief with no recorded source


@pytest.mark.parametrize(
    "typed",
    [
        PASTED_COMPLETE,  # already has its own text, type and layout
        "A woman holds a ring. Headline 'Make it perfect' top left.",  # short, but it says what text to print
        "Ring on velvet with a gold gradient overlay and a CTA button",
        "x" * 300,  # long
        "",
    ],
)
def test_a_complete_or_long_prompt_is_still_sent_as_written(typed):
    assert not ad.scene_may_be_redesigned({"prompt": typed, "prompt_source": "user"}, verbatim_slot=True)


def test_a_short_typed_prompt_gets_copy_design_brand_style_and_the_chosen_shot_style():
    prompt, label = ad.compose(
        scene_source="woman holding a ring in a boutique", seed="b", index=0,
        hook="The one she'll wear every day", headline="Make it perfect", cta="Book a Consultation",
        primary="#DBB45A", secondary="#000000", font_heading="Cormorant Garamond", font_body="Open Sans",
        focus="with_person", brand_name="Adoria Jewels", audience={"audience_type": "Women", "geography": "Melbourne VIC"},
    )
    assert "woman holding a ring in a boutique" in prompt and f"Design direction, {label}" in prompt
    assert 'headline "Make it perfect"' in prompt and 'button reading "Book a Consultation"' in prompt
    assert "primary #DBB45A (gold)" in prompt and "Cormorant Garamond (an elegant high-contrast display serif)" in prompt
    assert "A real person is the main subject, with the product clearly visible." in prompt
    assert "cast them naturally for Women in Melbourne VIC" in prompt and prompt.endswith(still.NO_LOGO_SHORT)
    assert "The product itself is the hero" in ad.compose(scene_source="a ring on velvet", seed="b", index=0, focus="product_only")[0]
    assert "main subject" not in ad.compose(scene_source="a ring on velvet", seed="b", index=0, focus="")[0]


def test_an_ai_draft_with_no_recorded_source_is_still_recognised_by_its_generated_at_stamp():
    long_ai = "Problem-agitate-solve commercial photography. " + "SUBJECT: a stressed business owner at a desk. " * 30
    stamped = {"prompt": long_ai, "generated_at": "2026-11-19T06:06:51.428Z"}
    assert ad.scene_may_be_redesigned(stamped, verbatim_slot=True)
    assert not ad.scene_may_be_redesigned({"prompt": long_ai}, verbatim_slot=True)  # nothing says the AI wrote it
    assert not ad.scene_may_be_redesigned({**stamped, "prompt_source": "user"}, verbatim_slot=True)  # a hand edit wins
    assert ad.scene_may_be_redesigned({**stamped, "prompt_source": "ai"}, verbatim_slot=True)


def test_the_brief_copy_keeps_the_brand_name_while_the_rest_of_the_prompt_loses_it():
    from app.services.ad_image_logo import guard_body

    prompt = (
        "Creative 3: Stop Watering.\n"
        'Main headline: "TIRED OF WATERING YOUR GARDEN?"\n'
        "Subheadline: Make watering smarter with WaterUps wicking technology.\n"
        "Visual direction:\nA WaterUps logo top left. A thriving garden by WaterUps.\n"
        'CTA button: "FIND YOUR WATERUPS SOLUTION"'
    )
    out = guard_body(prompt, "WaterUps")
    assert "Subheadline: Make watering smarter with WaterUps wicking technology." in out
    assert 'CTA button: "FIND YOUR WATERUPS SOLUTION"' in out
    assert "logo" not in out.lower()  # the logo sentence is still removed
    assert "A thriving garden by WaterUps" not in out  # a stand-alone mention outside the copy is still removed
