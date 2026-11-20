from app.services.icp_image_plan_service import enforce_no_spurious_circled_paper_prop as ban

SCENE = (
    "A dark desk. A leather-bound notepad shows a handwritten column of figures with circled amounts. "
    "A crumpled printed Google Ads invoice sits beside it. A phone shows a notification."
)


def test_a_scene_that_asks_for_a_notepad_and_invoice_is_not_told_to_leave_them_out():
    out = ban(SCENE, industry="retail", niche="google ads agency")
    assert "PROP BAN" not in out and "notepad" in out and "invoice" in out


def test_an_earlier_ban_is_removed_when_the_scene_wants_those_props():
    once = ban("A desk with a plain monitor.", industry="retail", niche="x")
    assert "PROP BAN" in once
    with_props = ban(once + " Add a crumpled invoice beside the keyboard.", industry="retail", niche="x")
    assert "PROP BAN" not in with_props and "crumpled invoice" in with_props


def test_a_scene_with_no_such_props_still_gets_the_guard():
    assert "PROP BAN" in ban("A smiling plumber holding a wrench.", industry="plumbing", niche="plumber")
