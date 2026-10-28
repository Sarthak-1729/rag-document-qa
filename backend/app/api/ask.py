from fastapi import APIRouter, Depends, HTTPException

from app.deps import AskServiceDep, ask_rate_limit
from app.llm.base import LLMError
from app.models import AskRequest, AskResponse, Source
from app.qa import NoDocuments

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskResponse, dependencies=[Depends(ask_rate_limit)])
def ask(body: AskRequest, service: AskServiceDep) -> AskResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Question must not be blank.")
    k = body.k or service.documents.settings.ask_top_k

    try:
        result = service.ask(question, k)
    except NoDocuments as exc:
        raise HTTPException(409, "No documents uploaded yet. Upload a PDF first.") from exc
    except LLMError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    return AskResponse(
        answer=result.answer,
        sources=[
            Source(n=n, doc_id=hit.doc_id, doc=hit.doc, page=hit.page, text=hit.text)
            for n, hit in enumerate(result.sources, start=1)
        ],
        refused=result.refused,
        refusal_reason=result.refusal_reason,
    )
