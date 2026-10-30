"""Download the evaluation PDFs from their official sources and verify their SHA-256.

All three are works of the U.S. Government, which are not subject to copyright in the
United States (17 U.S.C. § 105). The PDFs are not committed to git.

Usage (from backend/):  python -m eval.fetch_docs
"""

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

DOCS_DIR = Path(__file__).resolve().parent / "docs"


@dataclass(frozen=True)
class EvalDocument:
    filename: str
    title: str
    publisher: str
    url: str  # official URL (NIST URLs are where the publication DOIs resolve)
    sha256: str  # pinned when the question set was written (2026-10-30)


DOCUMENTS = [
    EvalDocument(
        filename="NIST.AI.100-1.pdf",
        title="Artificial Intelligence Risk Management Framework (AI RMF 1.0), NIST AI 100-1",
        publisher="NIST, January 2023 (doi:10.6028/NIST.AI.100-1)",
        url="https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf",
        sha256="7576edb531d9848825814ee88e28b1795d3a84b435b4b797d3670eafdc4a89f1",
    ),
    EvalDocument(
        filename="NIST.CSWP.29.pdf",
        title="The NIST Cybersecurity Framework (CSF) 2.0, NIST CSWP 29",
        publisher="NIST, February 26, 2024 (doi:10.6028/NIST.CSWP.29)",
        url="https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf",
        sha256="3c31f46fee98cac0c4323453e5109291a213b4de7fef8c058af9bf67f717433c",
    ),
    EvalDocument(
        filename="CDOC-110hdoc50.pdf",
        title="The Constitution of the United States of America, As Amended (H. Doc. 110-50)",
        publisher="U.S. Government Publishing Office via govinfo.gov, July 25, 2007",
        url="https://www.govinfo.gov/content/pkg/CDOC-110hdoc50/pdf/CDOC-110hdoc50.pdf",
        sha256="7f29c4a79e310cc7bcee5f3fd07fb1367e463bd4530fa5d854ebdd4fd4402e57",
    ),
]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_valid(doc: EvalDocument) -> bool:
    path = DOCS_DIR / doc.filename
    return path.exists() and sha256_of(path) == doc.sha256


def fetch(doc: EvalDocument) -> None:
    path = DOCS_DIR / doc.filename
    if is_valid(doc):
        print(f"ok        {doc.filename} (already downloaded, hash matches)")
        return
    tmp = path.with_suffix(".part")
    with httpx.stream(
        "GET",
        doc.url,
        follow_redirects=True,
        timeout=120,
        headers={"User-Agent": "rag-document-qa-eval/0.1"},
    ) as response:
        response.raise_for_status()
        with tmp.open("wb") as f:
            for block in response.iter_bytes():
                f.write(block)
    actual = sha256_of(tmp)
    if actual != doc.sha256:
        tmp.unlink()
        raise SystemExit(
            f"SHA-256 mismatch for {doc.filename}:\n  expected {doc.sha256}\n  got      {actual}\n"
            "The publisher may have changed the file. Page numbers in questions.json would "
            "need re-checking before updating the pinned hash."
        )
    tmp.replace(path)
    print(f"download  {doc.filename} ({path.stat().st_size:,} bytes, hash matches)")


def ensure_documents() -> list[Path]:
    """Return local paths, or exit with instructions if any file is missing or altered."""
    missing = [d.filename for d in DOCUMENTS if not is_valid(d)]
    if missing:
        raise SystemExit(f"Missing or altered eval PDFs: {missing}. Run: python -m eval.fetch_docs")
    return [DOCS_DIR / d.filename for d in DOCUMENTS]


def main() -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    for doc in DOCUMENTS:
        print(f"{doc.title}\n  {doc.url}")
        fetch(doc)
    sys.exit(0)


if __name__ == "__main__":
    main()
