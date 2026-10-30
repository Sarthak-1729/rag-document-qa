"""Question answering: retrieve, prompt the LLM, and attach server-verified citations."""

import re
from dataclasses import dataclass, field
from typing import Literal

from app.llm.base import LLMProvider
from app.llm.prompts import REFUSAL_ANSWER, SYSTEM_PROMPT, build_user_prompt
from app.retrieval.vector_store import SearchHit
from app.services import DocumentService

RefusalReason = Literal["low_relevance", "model", "uncited"]

# [1], [2, 3], [1,2]. One or two digits only, so years like [2024] are left alone.
_CITATION = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")
_REFUSAL_PREFIXES = ("i don't know", "i do not know")


class NoDocuments(Exception):
    pass


@dataclass
class AskResult:
    answer: str
    sources: list[SearchHit] = field(default_factory=list)
    refusal_reason: RefusalReason | None = None

    @property
    def refused(self) -> bool:
        return self.refusal_reason is not None


def is_refusal(answer: str) -> bool:
    normalized = answer.strip().lower().replace("’", "'")  # curly apostrophe
    return normalized.startswith(_REFUSAL_PREFIXES)


def resolve_citations(answer: str, hits: list[SearchHit]) -> tuple[str, list[SearchHit]]:
    """Keep only citations that point at real chunks and renumber them 1..n by first use.

    Returns the rewritten answer and the cited chunks in citation order. Sources come from
    our own retrieval results, so doc names and page numbers can't be invented by the model.
    """
    renumber: dict[int, int] = {}
    cited: list[SearchHit] = []

    def replace(match: re.Match[str]) -> str:
        parts = []
        for raw in match.group(1).split(","):
            n = int(raw)
            if not 1 <= n <= len(hits):
                continue  # the model cited a chunk that doesn't exist: drop it
            if n not in renumber:
                cited.append(hits[n - 1])
                renumber[n] = len(cited)
            marker = f"[{renumber[n]}]"
            if marker not in parts:  # "[1, 1]" -> "[1]"
                parts.append(marker)
        return "".join(parts)

    rewritten = _CITATION.sub(replace, answer)
    rewritten = re.sub(r"(\[\d+\])(?:\1)+", r"\1", rewritten)  # "[2][2]" -> "[2]"
    rewritten = re.sub(r"[ \t]+([.,;:])", r"\1", rewritten)  # tidy "word [9]." -> "word."
    return rewritten.strip(), cited


class AskService:
    def __init__(
        self,
        documents: DocumentService,
        llm: LLMProvider,
        min_relevance_score: float | None,
    ) -> None:
        self.documents = documents
        self.llm = llm
        self.min_relevance_score = min_relevance_score

    def ask(self, question: str, k: int) -> AskResult:
        if self.documents.store.count() == 0:
            raise NoDocuments
        hits = self.documents.search(question, k)

        threshold = self.min_relevance_score
        if not hits or (threshold is not None and hits[0].score < threshold):
            return AskResult(REFUSAL_ANSWER, refusal_reason="low_relevance")

        raw = self.llm.generate(SYSTEM_PROMPT, build_user_prompt(question, hits))
        if is_refusal(raw):
            return AskResult(REFUSAL_ANSWER, refusal_reason="model")

        answer, cited = resolve_citations(raw, hits)
        if not cited:
            # An answer we can't trace to a source breaks the app's promise: refuse instead.
            return AskResult(REFUSAL_ANSWER, refusal_reason="uncited")
        return AskResult(answer, cited)
