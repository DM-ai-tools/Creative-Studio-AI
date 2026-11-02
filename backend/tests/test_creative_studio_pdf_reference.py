from __future__ import annotations

from io import BytesIO
import sys
import types

from PIL import Image
from reportlab.pdfgen import canvas

from app.services.creative_studio_pdf_reference import ingest_landing_page_pdf
from app.services.file_service import file_service


def _sample_pdf(page_count: int = 2) -> bytes:
    out = BytesIO()
    pdf = canvas.Canvas(out)
    for index in range(page_count):
        pdf.drawString(72, 760, f"Traffic Radius landing page {index + 1}")
        pdf.drawString(72, 740, "Free Google Ads audit")
        pdf.showPage()
    pdf.save()
    return out.getvalue()


def test_ingest_landing_page_pdf_extracts_text_and_page_visuals(tmp_path, monkeypatch):
    class FakeBitmap:
        def to_pil(self):
            return Image.new("RGB", (320, 480), "white")

    class FakePage:
        def render(self, scale=1.5):
            assert scale == 1.5
            return FakeBitmap()

        def close(self):
            return None

    class FakeDocument:
        def __init__(self, content):
            assert content.startswith(b"%PDF")

        def __getitem__(self, _index):
            return FakePage()

        def close(self):
            return None

    monkeypatch.setitem(
        sys.modules,
        "pypdfium2",
        types.SimpleNamespace(PdfDocument=FakeDocument),
    )
    monkeypatch.setattr(file_service, "upload_dir", tmp_path)

    result = ingest_landing_page_pdf(
        content=_sample_pdf(),
        filename="landing-page.pdf",
        tenant_id="tenant-1",
    )

    assert result["name"] == "landing-page.pdf"
    assert result["page_count"] == 2
    assert "Free Google Ads audit" in result["text"]
    assert len(result["pages"]) == 2
    assert all(page["image_url"].endswith(".jpg") for page in result["pages"])
    assert "Traffic Radius landing page" in result["pages"][0]["text"]
    assert result["pdf_url"].endswith(".pdf")


def test_ingest_accepts_more_than_twelve_pages(tmp_path, monkeypatch):
    class FakeBitmap:
        def to_pil(self):
            return Image.new("RGB", (160, 240), "white")

    class FakePage:
        def render(self, scale=1.5):
            return FakeBitmap()

        def close(self):
            return None

    class FakeDocument:
        def __init__(self, _content):
            pass

        def __getitem__(self, _index):
            return FakePage()

        def close(self):
            return None

    monkeypatch.setitem(
        sys.modules,
        "pypdfium2",
        types.SimpleNamespace(PdfDocument=FakeDocument),
    )
    monkeypatch.setattr(file_service, "upload_dir", tmp_path)

    result = ingest_landing_page_pdf(
        content=_sample_pdf(13),
        filename="long-landing-page.pdf",
        tenant_id="tenant-1",
    )

    assert result["page_count"] == 13
    assert len(result["pages"]) == 13
