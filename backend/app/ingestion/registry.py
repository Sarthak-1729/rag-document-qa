"""A small JSON file listing uploaded documents (the vectors themselves live in Chroma)."""

import os
import threading
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, TypeAdapter


class DocumentRecord(BaseModel):
    id: str
    filename: str
    sha256: str
    pages: int
    chunks: int
    uploaded_at: datetime


_records = TypeAdapter(list[DocumentRecord])


class DocumentRegistry:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[DocumentRecord]:
        if not self._path.exists():
            return []
        return _records.validate_json(self._path.read_bytes())

    def _save(self, records: list[DocumentRecord]) -> None:
        # Write to a temp file then rename, so a crash never leaves half a JSON file.
        tmp = self._path.with_suffix(".tmp")
        tmp.write_bytes(_records.dump_json(records, indent=2))
        os.replace(tmp, self._path)

    def list(self) -> list[DocumentRecord]:
        with self._lock:
            return self._load()

    def get(self, doc_id: str) -> DocumentRecord | None:
        return next((r for r in self.list() if r.id == doc_id), None)

    def find_by_hash(self, sha256: str) -> DocumentRecord | None:
        return next((r for r in self.list() if r.sha256 == sha256), None)

    def add(self, record: DocumentRecord) -> None:
        with self._lock:
            self._save([*self._load(), record])

    def remove(self, doc_id: str) -> bool:
        with self._lock:
            records = self._load()
            kept = [r for r in records if r.id != doc_id]
            if len(kept) == len(records):
                return False
            self._save(kept)
            return True
