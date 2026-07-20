"""Extracts raw text from uploaded documents (PDF / Markdown)."""
from __future__ import annotations

import io
from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}


class UnsupportedFileTypeError(ValueError):
    pass


def extract_text(filename: str, raw_bytes: bytes) -> str:
    """Extract plain text from PDF or Markdown/text bytes.

    Raises UnsupportedFileTypeError for anything else.
    """
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf_text(raw_bytes)
    if suffix in {".md", ".markdown", ".txt"}:
        return _extract_plain_text(raw_bytes)

    raise UnsupportedFileTypeError(
        f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
    )


def _extract_pdf_text(raw_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _extract_plain_text(raw_bytes: bytes) -> str:
    return raw_bytes.decode("utf-8", errors="replace").strip()


def clean_text(text: str) -> str:
    """Light normalization: collapse excess whitespace, strip control chars."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)
