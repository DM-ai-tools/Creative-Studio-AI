"""Extract plain text from PDF uploads (brief / HeyGen script)."""

from __future__ import annotations

import re
from io import BytesIO

MAX_CHARS = 60_000
MAX_BYTES = 10 * 1024 * 1024


def extract_text_from_pdf_bytes(data: bytes, *, max_chars: int = MAX_CHARS) -> str:
    if len(data) > MAX_BYTES:
        raise ValueError("PDF exceeds 10 MB limit")
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pypdf is not installed") from exc

    reader = PdfReader(BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    text = "\n".join(parts).strip()
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    if not text:
        raise ValueError("No readable text found in this PDF")
    return text[:max_chars]
