from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.deps import DocumentServiceDep
from app.ingestion.validation import UploadRejected, read_limited, sanitize_filename
from app.models import DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=list[DocumentOut], status_code=status.HTTP_201_CREATED)
def upload_documents(
    service: DocumentServiceDep,
    files: Annotated[list[UploadFile], File(description="One or more PDF files")],
) -> list[DocumentOut]:
    settings = service.settings
    if len(files) > settings.max_files_per_upload:
        raise HTTPException(400, f"Upload at most {settings.max_files_per_upload} files at once.")

    try:
        # Validate and parse every file first, so one bad file rejects the whole batch
        # before anything is stored.
        prepared, seen_hashes = [], set()
        for upload in files:
            filename = sanitize_filename(upload.filename)
            data = read_limited(upload.file, settings.max_upload_bytes, filename)
            doc = service.prepare(filename, data, seen_hashes)
            seen_hashes.add(doc.sha256)
            prepared.append(doc)
    except UploadRejected as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    return [DocumentOut.model_validate(service.commit(doc).model_dump()) for doc in prepared]


@router.get("", response_model=list[DocumentOut])
def list_documents(service: DocumentServiceDep) -> list[DocumentOut]:
    return [DocumentOut.model_validate(r.model_dump()) for r in service.list_documents()]


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: str, service: DocumentServiceDep) -> Response:
    if not service.delete(doc_id):
        raise HTTPException(404, "Document not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
