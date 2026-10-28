from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import ask, documents, health, search
from app.config import Settings, get_settings
from app.llm.base import LLMProvider
from app.llm.factory import build_provider
from app.qa import AskService
from app.ratelimit import RateLimiter
from app.retrieval.embeddings import Embedder, SentenceTransformerEmbedder
from app.services import DocumentService


def create_app(
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    llm: LLMProvider | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own settings (temp dirs), a fake embedder and fake LLM."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Loading the embedding model takes a few seconds, so do it once at startup.
        model = embedder or SentenceTransformerEmbedder(settings.embedding_model)
        app.state.documents = DocumentService(settings, model)
        app.state.ask = AskService(
            app.state.documents, llm or build_provider(settings), settings.min_relevance_score
        )
        app.state.ask_limiter = RateLimiter(settings.ask_rate_limit_per_minute)
        yield

    app = FastAPI(
        title="RAG Document Q&A",
        description="Ask questions about uploaded PDFs and get answers with citations.",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(search.router)
    app.include_router(ask.router)
    return app


app = create_app()
