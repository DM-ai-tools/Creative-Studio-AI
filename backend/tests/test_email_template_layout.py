from app.services.email_template_layout_service import extract_palette_from_html, public_layout_base


def test_extract_palette_from_email_html():
    html = '<html><body style="background:#F5F5F2;color:#202124"><a style="background:#A3D16B">CTA</a></body></html>'
    palette = extract_palette_from_html(html)
    assert palette["primary_color"] in {"#F5F5F2", "#202124", "#A3D16B"}
    assert palette["secondary_color"] in {"#202124", "#A3D16B", "#F5F5F2", None}


def test_public_layout_base_shape():
    row = public_layout_base({"email_layout_base": {"label": "Newsletter shell", "layout_image_url": "/files/x.png"}})
    assert row["label"] == "Newsletter shell"
    assert row["layout_image_url"] == "/files/x.png"
