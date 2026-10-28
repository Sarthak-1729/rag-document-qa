"""Chroma wrapper: store chunk vectors with their metadata and run similarity search."""

from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.ingestion.chunker import Chunk

COLLECTION = "chunks"


@dataclass(frozen=True)
class SearchHit:
    doc_id: str
    doc: str
    page: int
    text: str
    score: float  # cosine similarity, higher is more relevant


class VectorStore:
    def __init__(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        # We pass our own embeddings, so no embedding function is attached.
        self._collection = client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def add_chunks(
        self, doc_id: str, filename: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        if not chunks:
            return
        self._collection.add(
            ids=[f"{doc_id}:{c.page}:{c.index}" for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {"doc_id": doc_id, "doc": filename, "page": c.page, "chunk": c.index}
                for c in chunks
            ],
        )

    def delete_document(self, doc_id: str) -> None:
        self._collection.delete(where={"doc_id": doc_id})

    def count(self) -> int:
        return self._collection.count()

    def search(self, query_embedding: list[float], k: int) -> list[SearchHit]:
        total = self.count()
        if total == 0:
            return []
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, total),
            include=["documents", "metadatas", "distances"],
        )
        return [
            SearchHit(
                doc_id=meta["doc_id"],
                doc=meta["doc"],
                page=int(meta["page"]),
                text=text,
                score=round(1.0 - distance, 4),  # Chroma returns cosine *distance*
            )
            for text, meta, distance in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True
            )
        ]
