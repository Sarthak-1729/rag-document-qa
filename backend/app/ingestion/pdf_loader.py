"""Extract text from a PDF, one entry per page."""

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfExtractionError(ValueError):
    """The file is not a usable PDF (corrupt, encrypted, or has no text layer)."""


@dataclass(frozen=True)
class PageText:
    page: int  # 1-based physical page index (what a PDF viewer shows), not the printed number
    text: str


def extract_pages(path: Path) -> list[PageText]:
    try:
        reader = PdfReader(path)
    except (PdfReadError, OSError) as exc:
        raise PdfExtractionError("File could not be read as a PDF.") from exc

    if reader.is_encrypted:
        raise PdfExtractionError("Encrypted PDFs are not supported.")

    pages = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pypdf can raise many types on malformed pages
            raise PdfExtractionError(f"Could not extract text from page {index}.") from exc
        pages.append(PageText(page=index, text=text))

    if not any(p.text.strip() for p in pages):
        raise PdfExtractionError("No extractable text found (scanned PDFs need OCR).")
    return pages
