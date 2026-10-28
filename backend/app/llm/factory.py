from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.gemini import GeminiProvider
from app.llm.ollama import OllamaProvider


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "gemini":
        assert settings.gemini_api_key is not None  # enforced by Settings validation
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            max_tokens=settings.llm_max_tokens,
            thinking_level=settings.gemini_thinking_level or None,
            timeout=settings.llm_timeout_seconds,
        )
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        max_tokens=settings.llm_max_tokens,
        num_ctx=settings.ollama_num_ctx,
        timeout=settings.llm_timeout_seconds,
    )
