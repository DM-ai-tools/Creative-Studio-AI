"""Deterministic landing-page PDF ingestion for Creative Studio.

The original PDF is retained for audit/download, while bounded page previews are
rendered as ordinary images that video providers can safely consume.  The raw
PDF is never forwarded to Seedance, Gemini, or image generation providers.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from pypdf import PdfReader

from app.services.file_service import file_service


MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_PAGES = 50
MAX_TEXT_CHARS = 80_000
MAX_VISUAL_PAGES = 50
MAX_PAGE_TEXT_CHARS = 1_500


def _clean_text(value: str) -> str:
    return "\n".join(line.rstrip() for line in (value or "").splitlines()).strip()


def ingest_landing_page_pdf(
    *,
    content: bytes,
    filename: str,
    tenant_id: str,
) -> dict[str, Any]:
    if not content:
        raise HTTPException(status_code=422, detail="The PDF is empty.")
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Landing-page PDF is too large. Maximum size is 50 MB.",
        )
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="Upload a valid PDF file.")

    try:
        reader = PdfReader(BytesIO(content))
        page_count = len(reader.pages)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The PDF could not be read.") from exc

    if page_count < 1:
        raise HTTPException(status_code=422, detail="The PDF has no pages.")
    if page_count > MAX_PAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Landing-page PDFs support up to {MAX_PAGES} pages.",
        )

    chunks: list[str] = []
    page_texts: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = _clean_text(page.extract_text() or "")
        except Exception:
            text = ""
        page_texts.append(text[:MAX_PAGE_TEXT_CHARS])
        if text:
            chunks.append(f"[Page {index}]\n{text}")
    extracted_text = "\n\n".join(chunks)[:MAX_TEXT_CHARS]

    original = file_service.save_bytes(
        content,
        tenant_id,
        "creative-studio-pdf-references",
        ".pdf",
        "application/pdf",
    )

    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise HTTPException(
            status_code=503,
            detail="PDF page rendering is unavailable. Install pypdfium2 and retry.",
        ) from exc

    pages: list[dict[str, Any]] = []
    try:
        document = pdfium.PdfDocument(content)
        for index in range(min(page_count, MAX_VISUAL_PAGES)):
            page = document[index]
            bitmap = page.render(scale=1.5)
            image = bitmap.to_pil().convert("RGB")
            out = BytesIO()
            image.save(out, format="JPEG", quality=88, optimize=True)
            saved = file_service.save_bytes(
                out.getvalue(),
                tenant_id,
                "creative-studio-pdf-references/pages",
                ".jpg",
                "image/jpeg",
            )
            pages.append(
                {
                    "page_number": index + 1,
                    "image_url": saved["file_url"],
                    "width": image.width,
                    "height": image.height,
                    "text": page_texts[index] if index < len(page_texts) else "",
                }
            )
            close_bitmap = getattr(bitmap, "close", None)
            if callable(close_bitmap):
                close_bitmap()
            page.close()
        document.close()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="PDF pages could not be rendered.") from exc

    safe_name = Path(filename or "landing-page.pdf").name
    return {
        "name": safe_name,
        "pdf_url": original["file_url"],
        "page_count": page_count,
        "text": extracted_text,
        "pages": pages,
        "visual_pages_truncated": page_count > MAX_VISUAL_PAGES,
    }
