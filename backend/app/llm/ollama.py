"""Local LLM through Ollama's chat API: https://docs.ollama.com/api/chat"""

import httpx

from app.llm.base import LLMError


class OllamaProvider:
    name = "ollama"

    def __init__(
        self, base_url: str, model: str, max_tokens: int, num_ctx: int, timeout: float
    ) -> None:
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._max_tokens = max_tokens
        self._num_ctx = num_ctx
        self._timeout = timeout

    def generate(self, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": 0,  # we want faithful extraction, not creativity
                "num_predict": self._max_tokens,
                "num_ctx": self._num_ctx,  # the default window can silently cut off context
            },
        }
        try:
            response = httpx.post(self._url, json=payload, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise LLMError(504, "The local model (Ollama) timed out.") from exc
        except httpx.HTTPError as exc:
            raise LLMError(503, f"Ollama is not reachable at {self._url}. Is it running?") from exc

        if response.status_code == 404:
            raise LLMError(
                502, f"Ollama model '{self._model}' not found. Run: ollama pull {self._model}"
            )
        if response.status_code != 200:
            raise LLMError(502, f"Ollama returned HTTP {response.status_code}.")

        try:
            text = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError(502, "Ollama returned an unexpected response.") from exc
        if not isinstance(text, str) or not text.strip():
            raise LLMError(502, "Ollama returned an empty answer.")
        return text.strip()
