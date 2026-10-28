"""Split page text into overlapping chunks that fit the embedding model's input limit."""

import re
from dataclasses import dataclass

from app.ingestion.pdf_loader import PageText

# Preferred places to cut, best first: paragraph break, sentence end, any whitespace.
_BOUNDARIES = (re.compile(r"\n\s*\n"), re.compile(r"[.!?]\s"), re.compile(r"\s"))


@dataclass(frozen=True)
class Chunk:
    page: int
    index: int  # position of this chunk within its page
    text: str


def normalize(text: str) -> str:
    """Collapse runs of spaces/tabs and blank lines that PDF extraction leaves behind."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _find_cut(text: str, start: int, end: int, min_size: int) -> int:
    """Return the best cut position in text[start:end], never before start + min_size."""
    window = text[start:end]
    for pattern in _BOUNDARIES:
        matches = [m.end() for m in pattern.finditer(window) if m.end() >= min_size]
        if matches:
            return start + matches[-1]
    return end  # no boundary at all (e.g. one very long token): hard cut


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    text = normalize(text)
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Don't accept a cut so early that the chunk is mostly overlap.
            end = _find_cut(text, start, end, min_size=chunk_size // 2)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        next_start = end - overlap
        # Start the overlap at a word boundary so chunks don't begin mid-word.
        space = text.find(" ", next_start, end)
        start = space + 1 if space != -1 else next_start
    return chunks


def chunk_pages(pages: list[PageText], chunk_size: int, overlap: int) -> list[Chunk]:
    """Chunk each page separately so every chunk maps to exactly one page."""
    return [
        Chunk(page=page.page, index=i, text=piece)
        for page in pages
        for i, piece in enumerate(split_text(page.text, chunk_size, overlap))
    ]
