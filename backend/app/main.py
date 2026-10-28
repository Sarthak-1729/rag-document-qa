from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import documents, health, search
from app.config import Settings, get_settings
from app.retrieval.embeddings import Embedder, SentenceTransformerEmbedder
from app.services import DocumentService


def create_app(settings: Settings | None = None, embedder: Embedder | None = None) -> FastAPI:
    """Build the app. Tests pass their own settings (temp dirs) and a fake embedder."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Loading the embedding model takes a few seconds, so do it once at startup.
        model = embedder or SentenceTransformerEmbedder(settings.embedding_model)
        app.state.documents = DocumentService(settings, model)
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
    return app


app = create_app()
