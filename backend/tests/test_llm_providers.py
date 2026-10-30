"""Provider adapters tested against faked HTTP responses. No network calls are made."""

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.llm.base import LLMError
from app.llm.gemini import API_URL, GeminiProvider
from app.llm.ollama import OllamaProvider
from app.ratelimit import RateLimiter
from tests.helpers import FakePost


@pytest.fixture
def gemini():
    return GeminiProvider(SecretStr("test-key-123"), "gemini-test", 256, "minimal", timeout=5)


@pytest.fixture
def ollama():
    return OllamaProvider("http://ollama:11434/", "tiny", 256, 4096, timeout=5)


def gemini_body(text="Answer [1].", status="completed"):
    return {
        "status": status,
        "steps": [
            {"type": "thought", "summary": "thinking..."},
            {"type": "model_output", "content": [{"type": "text", "text": text}]},
        ],
    }


# --- Gemini ----------------------------------------------------------------------


def test_gemini_success_and_request_shape(monkeypatch, gemini):
    post = FakePost(json=gemini_body())
    monkeypatch.setattr(httpx, "post", post)

    assert gemini.generate("SYS", "USER") == "Answer [1]."
    call = post.calls[0]
    assert call["url"] == API_URL
    assert "test-key-123" not in call["url"]  # key travels in a header only
    assert call["headers"] == {"x-goog-api-key": "test-key-123"}
    assert call["json"] == {
        "model": "gemini-test",
        "system_instruction": "SYS",
        "input": "USER",
        "generation_config": {"max_output_tokens": 256, "thinking_level": "minimal"},
        "store": False,
    }


@pytest.mark.parametrize(
    ("status", "expected"),
    [(429, 503), (401, 502), (403, 502), (400, 502), (500, 503)],
)
def test_gemini_http_errors(monkeypatch, gemini, status, expected):
    monkeypatch.setattr(httpx, "post", FakePost(status, {"error": {"message": "nope"}}))
    with pytest.raises(LLMError) as err:
        gemini.generate("s", "u")
    assert err.value.status_code == expected
    assert "test-key-123" not in err.value.detail


def test_gemini_timeout(monkeypatch, gemini):
    monkeypatch.setattr(httpx, "post", FakePost(exc=httpx.ReadTimeout("slow")))
    with pytest.raises(LLMError) as err:
        gemini.generate("s", "u")
    assert err.value.status_code == 504


@pytest.mark.parametrize("body", [gemini_body(status="incomplete"), gemini_body(text="  ")])
def test_gemini_incomplete_or_empty(monkeypatch, gemini, body):
    monkeypatch.setattr(httpx, "post", FakePost(json=body))
    with pytest.raises(LLMError) as err:
        gemini.generate("s", "u")
    assert err.value.status_code == 502


def test_gemini_requires_api_key():
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        Settings(_env_file=None, llm_provider="gemini", gemini_api_key="")


def test_settings_repr_hides_api_key():
    settings = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="super-secret")
    assert "super-secret" not in repr(settings)


# --- Ollama ----------------------------------------------------------------------


def test_ollama_success_and_request_shape(monkeypatch, ollama):
    post = FakePost(json={"message": {"role": "assistant", "content": " Hi [1]. "}, "done": True})
    monkeypatch.setattr(httpx, "post", post)

    assert ollama.generate("SYS", "USER") == "Hi [1]."
    call = post.calls[0]
    assert call["url"] == "http://ollama:11434/api/chat"
    assert call["json"]["stream"] is False
    assert call["json"]["messages"][0] == {"role": "system", "content": "SYS"}
    assert call["json"]["options"]["num_predict"] == 256


def test_ollama_missing_model_hint(monkeypatch, ollama):
    monkeypatch.setattr(httpx, "post", FakePost(404, {"error": "model not found"}))
    with pytest.raises(LLMError, match="ollama pull tiny"):
        ollama.generate("s", "u")


def test_ollama_not_running(monkeypatch, ollama):
    monkeypatch.setattr(httpx, "post", FakePost(exc=httpx.ConnectError("refused")))
    with pytest.raises(LLMError) as err:
        ollama.generate("s", "u")
    assert err.value.status_code == 503


# --- Rate limiter ----------------------------------------------------------------


def test_rate_limiter_sliding_window():
    now = [0.0]
    limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    assert limiter.check("ip") is None
    assert limiter.check("ip") is None
    assert limiter.check("ip") == pytest.approx(60)
    assert limiter.check("other-ip") is None  # limits are per client
    now[0] = 60.0
    assert limiter.check("ip") is None  # oldest request left the window


def test_rate_limiter_disabled_when_zero():
    limiter = RateLimiter(limit=0)
    assert all(limiter.check("ip") is None for _ in range(100))
