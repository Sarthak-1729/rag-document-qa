from fastapi import APIRouter

from app import __version__
from app.deps import DocumentServiceDep
from app.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(service: DocumentServiceDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        llm_provider=service.settings.llm_provider,
        documents=len(service.list_documents()),
    )
