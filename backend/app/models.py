"""Request and response schemas shared by the API routes."""

from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_provider: str
    documents: int


class DocumentOut(BaseModel):
    id: str
    filename: str
    pages: int
    chunks: int
    uploaded_at: datetime


class SearchResult(BaseModel):
    doc_id: str
    doc: str
    page: int  # 1-based physical page index in the PDF
    text: str
    score: float  # cosine similarity in [-1, 1]; higher is more relevant


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
