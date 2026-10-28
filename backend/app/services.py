"""Glue between the API and the ingestion/retrieval building blocks."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.ingestion.chunker import Chunk, chunk_pages
from app.ingestion.pdf_loader import PdfExtractionError, extract_pages
from app.ingestion.registry import DocumentRecord, DocumentRegistry
from app.ingestion.validation import UploadRejected
from app.retrieval.embeddings import Embedder
from app.retrieval.vector_store import SearchHit, VectorStore


@dataclass
class PreparedDocument:
    """A validated upload whose text is extracted and chunked, but not yet stored."""

    id: str
    filename: str
    sha256: str
    data: bytes
    pages: int
    chunks: list[Chunk]


class DocumentService:
    def __init__(self, settings: Settings, embedder: Embedder) -> None:
        self.settings = settings
        self.embedder = embedder
        self.store = VectorStore(settings.chroma_dir)
        self.registry = DocumentRegistry(settings.registry_path)
        settings.upload_dir.mkdir(parents=True, exist_ok=True)

    def _pdf_path(self, doc_id: str) -> Path:
        return self.settings.upload_dir / f"{doc_id}.pdf"

    def prepare(self, filename: str, data: bytes, seen_hashes: set[str]) -> PreparedDocument:
        """Validate and parse one upload. Nothing is written yet, so failures leave no trace."""
        sha256 = hashlib.sha256(data).hexdigest()
        existing = self.registry.find_by_hash(sha256)
        if existing or sha256 in seen_hashes:
            name = existing.filename if existing else filename
            raise UploadRejected(409, f"'{filename}' was already uploaded as '{name}'.")

        doc_id = uuid.uuid4().hex
        # pypdf reads from a path, so parse from a temp file next to the final location.
        tmp_path = self.settings.upload_dir / f"{doc_id}.part"
        tmp_path.write_bytes(data)
        try:
            pages = extract_pages(tmp_path)
        except PdfExtractionError as exc:
            raise UploadRejected(422, f"'{filename}': {exc}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)

        chunks = chunk_pages(pages, self.settings.chunk_size, self.settings.chunk_overlap)
        return PreparedDocument(doc_id, filename, sha256, data, len(pages), chunks)

    def commit(self, doc: PreparedDocument) -> DocumentRecord:
        """Embed and store a prepared document; roll back partial writes on failure."""
        pdf_path = self._pdf_path(doc.id)
        try:
            pdf_path.write_bytes(doc.data)
            embeddings = self.embedder.embed_documents([c.text for c in doc.chunks])
            self.store.add_chunks(doc.id, doc.filename, doc.chunks, embeddings)
            record = DocumentRecord(
                id=doc.id,
                filename=doc.filename,
                sha256=doc.sha256,
                pages=doc.pages,
                chunks=len(doc.chunks),
                uploaded_at=datetime.now(UTC),
            )
            self.registry.add(record)
            return record
        except Exception:
            self.store.delete_document(doc.id)
            pdf_path.unlink(missing_ok=True)
            raise

    def list_documents(self) -> list[DocumentRecord]:
        return self.registry.list()

    def delete(self, doc_id: str) -> bool:
        if self.registry.get(doc_id) is None:
            return False
        # Remove vectors and file first: if that fails, the document stays listed and
        # the user can retry, instead of leaving orphaned chunks that still show up in search.
        self.store.delete_document(doc_id)
        self._pdf_path(doc_id).unlink(missing_ok=True)
        self.registry.remove(doc_id)
        return True

    def search(self, query: str, k: int) -> list[SearchHit]:
        return self.store.search(self.embedder.embed_query(query), k)
