"""Checks applied to every uploaded file before we trust it."""

import re
import unicodedata
from typing import BinaryIO

PDF_MAGIC = b"%PDF-"
MAX_FILENAME_LENGTH = 120


class UploadRejected(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def sanitize_filename(raw: str | None) -> str:
    """Return a safe display name ending in .pdf, or raise UploadRejected.

    The name is only shown to users; files on disk are stored under a random id.
    """
    if not raw:
        raise UploadRejected(400, "File has no name.")
    # Drop any directory part a client might send (both / and \ separators).
    name = re.split(r"[\\/]", raw)[-1]
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[^\w.\- ()]", "_", name)  # keep letters, digits, _ . - space ( )
    name = re.sub(r"\s+", " ", name).strip(" .")

    stem, dot, ext = name.rpartition(".")
    if not dot or ext.lower() != "pdf" or not stem.strip(" ._"):
        raise UploadRejected(415, f"'{raw}' is not a .pdf file.")
    return stem[: MAX_FILENAME_LENGTH - 4].rstrip(" .") + ".pdf"


def read_limited(stream: BinaryIO, max_bytes: int, filename: str) -> bytes:
    """Read the whole upload, rejecting it as soon as it exceeds max_bytes."""
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadRejected(413, f"'{filename}' is larger than {max_bytes // (1024 * 1024)} MB.")
    if not data:
        raise UploadRejected(400, f"'{filename}' is empty.")
    if not data.startswith(PDF_MAGIC):
        raise UploadRejected(415, f"'{filename}' is not a valid PDF file.")
    return data
