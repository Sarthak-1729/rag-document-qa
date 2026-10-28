"""Request and response schemas shared by the API routes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    k: int | None = Field(default=None, ge=1, le=20, description="Chunks to retrieve")


class Source(BaseModel):
    n: int  # the [n] marker used in the answer
    doc_id: str
    doc: str
    page: int  # 1-based physical page index, taken from our metadata (never from the LLM)
    text: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    refused: bool
    # Why we refused: retrieval found nothing relevant, the model said it didn't know,
    # or the model answered without any valid citation.
    refusal_reason: Literal["low_relevance", "model", "uncited"] | None = None
