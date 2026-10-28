from typing import Annotated

from fastapi import Depends, Request

from app.services import DocumentService


def get_document_service(request: Request) -> DocumentService:
    return request.app.state.documents


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
