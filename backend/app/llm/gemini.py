"""Hosted LLM through the Gemini Interactions API.

Docs: https://ai.google.dev/gemini-api/docs/interactions
      https://ai.google.dev/api/interactions-api
"""

import httpx
from pydantic import SecretStr

from app.llm.base import LLMError

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        max_tokens: int,
        thinking_level: str | None,
        timeout: float,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._thinking_level = thinking_level
        self._timeout = timeout

    def generate(self, system: str, user: str) -> str:
        # max_output_tokens includes thinking tokens, so keep thinking low for this task.
        generation_config: dict[str, object] = {"max_output_tokens": self._max_tokens}
        if self._thinking_level:
            generation_config["thinking_level"] = self._thinking_level
        payload = {
            "model": self._model,
            "system_instruction": system,
            "input": user,
            "generation_config": generation_config,
            "store": False,  # don't keep document text on Google's servers
        }
        # The key goes in a header, not the URL, so it never shows up in request logs.
        headers = {"x-goog-api-key": self._api_key.get_secret_value()}
        try:
            response = httpx.post(API_URL, json=payload, headers=headers, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise LLMError(504, "Gemini timed out.") from exc
        except httpx.HTTPError as exc:
            raise LLMError(503, "Could not reach the Gemini API.") from exc

        if response.status_code != 200:
            raise _http_error(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise LLMError(502, "Gemini returned an unexpected response.") from exc

        status = body.get("status")
        if status == "incomplete":
            raise LLMError(502, "Gemini's answer was cut off; raise LLM_MAX_TOKENS.")
        if status != "completed":
            raise LLMError(502, f"Gemini did not complete the request (status: {status}).")

        text = "".join(
            part.get("text", "")
            for step in body.get("steps", [])
            if step.get("type") == "model_output"
            for part in step.get("content", [])
            if part.get("type") == "text"
        ).strip()
        if not text:
            raise LLMError(502, "Gemini returned an empty answer.")
        return text


def _http_error(response: httpx.Response) -> LLMError:
    try:
        message = response.json().get("error", {}).get("message", "")
    except ValueError:
        message = ""
    code = response.status_code
    if code == 429:
        return LLMError(503, "Gemini rate limit or free-tier quota reached. Try again later.")
    if code in (401, 403):
        return LLMError(502, "Gemini rejected the API key. Check GEMINI_API_KEY.")
    if code >= 500:
        return LLMError(503, "Gemini is temporarily unavailable.")
    return LLMError(502, f"Gemini request failed (HTTP {code}). {message}".strip())
