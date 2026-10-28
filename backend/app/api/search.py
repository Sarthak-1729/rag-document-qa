from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.deps import DocumentServiceDep
from app.models import SearchResponse, SearchResult

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    service: DocumentServiceDep,
    q: Annotated[str, Query(min_length=1, max_length=1000, description="Search query")],
    k: Annotated[int, Query(ge=1, le=20, description="Number of chunks to return")] = 5,
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(422, "Query must not be blank.")
    hits = service.search(query, k)
    return SearchResponse(
        query=query,
        results=[SearchResult(**hit.__dict__) for hit in hits],
    )
