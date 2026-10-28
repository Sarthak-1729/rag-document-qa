from typing import Annotated

from fastapi import Depends, Request

from app.qa import AskService
from app.services import DocumentService


def get_document_service(request: Request) -> DocumentService:
    return request.app.state.documents


def get_ask_service(request: Request) -> AskService:
    return request.app.state.ask


def ask_rate_limit(request: Request) -> None:
    request.app.state.ask_limiter(request)


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
AskServiceDep = Annotated[AskService, Depends(get_ask_service)]
