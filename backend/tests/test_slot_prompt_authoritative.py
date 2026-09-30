"""Per-variant prompt preservation for image generation."""

from app.services.icp_image_plan_service import (
    consolidate_image_prompt_for_generation,
    prepare_self_contained_slot_prompt,
    slot_prompt_is_authoritative,
    slot_prompt_is_self_contained,
)


def test_slot_prompt_is_authoritative_any_non_empty():
    assert not slot_prompt_is_authoritative("")
    assert not slot_prompt_is_authoritative("   ")
    assert slot_prompt_is_authoritative("short pasted prompt")
    assert slot_prompt_is_authoritative("A" * 40)


BLACK_TIE_PROMPT = """
Inside a well-appointed Black Tie Classic formalwear store.
TEXT ON IMAGE ONLY:
Upper headline:
"35+ YEARS SUITING UP MELBOURNE"
Centre supporting text:
"Wedding Specialists — Hire • Buy • Tailoring"
CTA:
"Book an Appointment"
TYPOGRAPHY — IMPORTANT FOR THE DESIGN APP:
Use Butler font for headlines and major display typography wherever available.
Typography colours: Headline and CTA accent #FB5A5F. Supporting text white or #39599E.
Brand identity: ONLY "Black Tie Classic" if a brand name appears.
""".strip()


def test_self_contained_chatgpt_prompt_detected():
    assert slot_prompt_is_self_contained(BLACK_TIE_PROMPT)
    assert not slot_prompt_is_self_contained("TEXT-ANCHOR: hook only")


def test_self_contained_prompt_passthrough():
    out = prepare_self_contained_slot_prompt(BLACK_TIE_PROMPT)
    assert "Butler font" in out
    assert "#FB5A5F" in out
    assert "TEXT ON IMAGE ONLY" in out
    assert "Tailoring" in out


def test_consolidate_preserves_saved_slot_prompt():
    scene = (
        "Modern retail hero — charcoal gradient lower third, headline in bold white sans-serif, "
        "CTA pill in brand blue #2563EB, product centered on marble surface, soft rim light."
    )
    processed = (
        f"{scene} ON-IMAGE TYPE STYLE: Modern retail ad typography — headline in clean white sans-serif. "
        "TEXT-ANCHOR: Upper: \"Stop Wasting Ad Spend\" Centre: \"Meta Ads That Convert\" CTA: \"Book Call\""
    )
    out = consolidate_image_prompt_for_generation(
        processed,
        scene_prompt=scene,
        image_hook="Stop Wasting Ad Spend",
        image_headline="Meta Ads That Convert",
        cta="Book Call",
        primary_color="#2563EB",
    )
    assert out == processed
    assert "ON-IMAGE TYPE STYLE" in out
    assert "charcoal gradient" in out
