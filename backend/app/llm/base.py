"""The interface every LLM backend implements, plus the error type the API layer understands."""

from typing import Protocol


class LLMError(Exception):
    """A provider failure, carrying the HTTP status our API should return for it."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class LLMProvider(Protocol):
    name: str

    def generate(self, system: str, user: str) -> str:
        """Return the model's text reply. Raise LLMError on any failure."""
        ...
