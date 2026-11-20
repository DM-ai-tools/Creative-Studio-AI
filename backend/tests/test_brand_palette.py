from app.services import ad_image_brand as ab

SNAP = {"primary_color": "#1D4ED8", "secondary_color": "#16A34A", "tertiary_color": "#F59E0B"}


def test_with_nothing_ticked_every_brand_colour_is_used():
    assert ab.select_palette(SNAP, {}) == ("#1D4ED8", "#16A34A", "#F59E0B", False)
    assert ab.select_palette(SNAP, None) == ("#1D4ED8", "#16A34A", "#F59E0B", False)


def test_ticking_two_or_one_colour_leaves_the_others_out_and_marks_it_a_subset():
    assert ab.select_palette(SNAP, {"palette": ["primary", "tertiary"]}) == ("#1D4ED8", "", "#F59E0B", True)
    assert ab.select_palette(SNAP, {"palette": ["secondary"]}) == ("", "#16A34A", "", True)


def test_a_colour_the_brand_does_not_have_is_skipped_and_all_ticked_is_not_a_subset():
    two = {"primary_color": "#1D4ED8", "secondary_color": "#16A34A"}
    assert ab.select_palette(two, {"palette": ["primary", "secondary", "tertiary"]}) == ("#1D4ED8", "#16A34A", "", False)
    assert ab.select_palette(two, {"palette": ["tertiary"]}) == ("#1D4ED8", "#16A34A", "", False)  # nothing valid: all


def test_the_prompt_names_the_third_colour_and_restricts_a_subset():
    full = ab.apply_brand_style("A planter.", primary="#1D4ED8", secondary="#16A34A", tertiary="#F59E0B")
    assert "tertiary #F59E0B" in full and "small accents" in full and "Use only these brand colours" not in full
    only = ab.apply_brand_style("A planter.", primary="#1D4ED8", tertiary="#F59E0B", only_these=True)
    assert "tertiary #F59E0B" in only and "secondary" not in only and "Use only these brand colours" in only


def test_the_brand_snapshot_carries_the_third_colour_from_the_brand_kit():
    from types import SimpleNamespace

    from app.services.brand_prompt import brand_snapshot

    brand = SimpleNamespace(name="B", industry="x", language="English", primary_color="#111111", secondary_color="#222222",
                            voice_rules={}, logo_url=None)
    kit = SimpleNamespace(colors={"tertiary": "#333333"}, fonts={}, logo_variations={})
    assert brand_snapshot(brand, kit)["tertiary_color"] == "#333333"
    assert brand_snapshot(brand, None)["tertiary_color"] == ""


def test_colour_codes_typed_on_a_variant_replace_the_brands_and_can_fill_a_missing_third():
    two = {"primary_color": "#1D4ED8", "secondary_color": "#16A34A"}
    slot = {"palette_colors": {"primary": "#ff0000", "tertiary": "#00ff00", "secondary": "nonsense"}}
    p, s, t, subset = ab.select_palette(two, slot)
    assert (p.upper(), s.upper(), t.upper(), subset) == ("#FF0000", "#16A34A", "#00FF00", False)
    ticked = {**slot, "palette": ["tertiary"]}
    assert ab.select_palette(two, ticked)[:3] == ("", "", t) and ab.select_palette(two, ticked)[3] is True
