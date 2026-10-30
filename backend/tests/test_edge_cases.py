"""Edge cases and failure paths not covered by the per-feature test files."""

import io
import sys
import types

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from pypdf import PageObject, PdfWriter

from app.config import BACKEND_DIR, Settings
from app.ingestion.chunker import Chunk
from app.llm.factory import build_provider
from app.llm.gemini import GeminiProvider
from app.llm.ollama import OllamaProvider
from app.main import create_app
from app.qa import AskService, resolve_citations
from app.retrieval.embeddings import SentenceTransformerEmbedder
from app.retrieval.vector_store import SearchHit, VectorStore
from tests.helpers import FakeLLM, FakePost, HashingEmbedder, make_pdf

PDF = make_pdf([["Volcanoes erupt when magma pressure builds."], ["Terns migrate far."]])


def upload(client, *files):
    return client.post("/documents", files=[("files", (n, d, "application/pdf")) for n, d in files])


def make_client(settings, llm=None, embedder=None, **kwargs) -> TestClient:
    app = create_app(
        settings=settings, embedder=embedder or HashingEmbedder(), llm=llm or FakeLLM()
    )
    return TestClient(app, **kwargs)


# --- Upload validation ---------------------------------------------------------------


def test_empty_file_is_rejected(client):
    assert upload(client, ("empty.pdf", b"")).status_code == 400


def test_too_many_files_in_one_request(client, settings):
    settings.max_files_per_upload = 1
    response = upload(client, ("a.pdf", PDF), ("b.pdf", make_pdf([["other"]])))
    assert response.status_code == 400
    assert client.get("/documents").json() == []


def test_same_file_twice_in_one_batch_is_a_duplicate(client):
    response = upload(client, ("a.pdf", PDF), ("copy.pdf", PDF))
    assert response.status_code == 409
    assert client.get("/documents").json() == []


def test_encrypted_pdf_is_rejected(client):
    writer = PdfWriter(clone_from=io.BytesIO(PDF))
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    response = upload(client, ("locked.pdf", buffer.getvalue()))
    assert response.status_code == 422
    assert "Encrypted" in response.json()["detail"]


def test_page_that_fails_extraction_is_rejected(client, monkeypatch):
    def broken(self, *args, **kwargs):
        raise RuntimeError("bad content stream")

    monkeypatch.setattr(PageObject, "extract_text", broken)
    response = upload(client, ("broken.pdf", PDF))
    assert response.status_code == 422
    assert "page 1" in response.json()["detail"]


def test_unsafe_filename_is_sanitized_and_not_used_on_disk(client, settings):
    [doc] = upload(client, ("../../evil<x>.pdf", PDF)).json()
    assert doc["filename"] == "evil_x_.pdf"
    assert [p.name for p in settings.upload_dir.iterdir()] == [f"{doc['id']}.pdf"]


def test_failed_embedding_rolls_back_everything(settings):
    class BrokenEmbedder(HashingEmbedder):
        def embed_documents(self, texts):
            raise RuntimeError("model crashed")

    with make_client(settings, embedder=BrokenEmbedder(), raise_server_exceptions=False) as client:
        assert upload(client, ("a.pdf", PDF)).status_code == 500
        assert client.get("/documents").json() == []
    assert list(settings.upload_dir.iterdir()) == []


def test_documents_survive_a_restart(settings):
    with make_client(settings) as client:
        [doc] = upload(client, ("a.pdf", PDF)).json()
    with make_client(settings) as client:  # new app, same data dir
        assert [d["id"] for d in client.get("/documents").json()] == [doc["id"]]
        hits = client.get("/search", params={"q": "volcanoes magma"}).json()["results"]
        assert hits[0]["page"] == 1


# --- /ask edge cases ---------------------------------------------------------------------


def hit(n: int) -> SearchHit:
    return SearchHit(doc_id="d", doc="a.pdf", page=n, text=f"t{n}", score=0.5)


def test_duplicate_citations_collapse_to_one_marker_and_one_source():
    answer, cited = resolve_citations("A [1, 1]. B [2][2][2]. C [1].", [hit(1), hit(2)])
    assert answer == "A [1]. B [2]. C [1]."
    assert [h.page for h in cited] == [1, 2]


def test_answer_citing_only_out_of_range_chunks_is_refused(client, fake_llm):
    upload(client, ("a.pdf", PDF))
    fake_llm.reply = "It erupts [0] because of pressure [42]."
    body = client.post("/ask", json={"question": "Why do volcanoes erupt?"}).json()
    assert body["refusal_reason"] == "uncited"


def test_empty_retrieval_refuses_without_calling_llm():
    class EmptyDocuments:
        class store:
            @staticmethod
            def count():
                return 5

        @staticmethod
        def search(question, k):
            return []

    llm = FakeLLM()
    result = AskService(EmptyDocuments(), llm, min_relevance_score=None).ask("q", 5)
    assert result.refusal_reason == "low_relevance"
    assert llm.calls == []


def test_ask_uses_configured_top_k(client, settings, fake_llm):
    settings.ask_top_k = 1
    upload(client, ("a.pdf", PDF))
    client.post("/ask", json={"question": "volcanoes"})
    assert fake_llm.calls[0][1].count("<chunk ") == 1


@pytest.mark.parametrize(
    ("fake_post", "status", "message"),
    [
        (FakePost(429, {"error": {"message": "quota"}}), 503, "quota"),
        (FakePost(401, {"error": {"message": "API key not valid"}}), 502, "GEMINI_API_KEY"),
        (FakePost(exc=httpx.ReadTimeout("slow")), 504, "timed out"),
        (FakePost(exc=httpx.ConnectError("down")), 503, "reach"),
    ],
)
def test_gemini_failures_through_ask_endpoint(settings, monkeypatch, fake_post, status, message):
    monkeypatch.setattr(httpx, "post", fake_post)
    gemini = GeminiProvider(SecretStr("k"), "m", 100, None, timeout=1)
    with make_client(settings, llm=gemini) as client:
        upload(client, ("a.pdf", PDF))
        response = client.post("/ask", json={"question": "volcanoes"})
    assert response.status_code == status
    assert message in response.json()["detail"]


def test_rate_limit_retry_after_is_readable_cross_origin(settings):
    settings.ask_rate_limit_per_minute = 1
    with make_client(settings) as client:
        upload(client, ("a.pdf", PDF))
        headers = {"Origin": "http://localhost:5173"}
        client.post("/ask", json={"question": "q"}, headers=headers)
        response = client.post("/ask", json={"question": "q"}, headers=headers)
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert "retry-after" in response.headers["access-control-expose-headers"].lower()


# --- Provider adapters: remaining error branches ------------------------------------------


@pytest.fixture
def gemini():
    return GeminiProvider(SecretStr("k"), "m", 100, "low", timeout=1)


@pytest.fixture
def ollama():
    return OllamaProvider("http://o:11434", "tiny", 100, 4096, timeout=1)


def test_gemini_failed_status_and_bad_json(monkeypatch, gemini):
    monkeypatch.setattr(httpx, "post", FakePost(json={"status": "failed", "steps": []}))
    with pytest.raises(Exception, match="did not complete"):
        gemini.generate("s", "u")

    def not_json(url, **kwargs):
        return httpx.Response(200, content=b"<html>", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", not_json)
    with pytest.raises(Exception, match="unexpected response"):
        gemini.generate("s", "u")


@pytest.mark.parametrize(
    ("fake_post", "status", "message"),
    [
        (FakePost(exc=httpx.ReadTimeout("slow")), 504, "timed out"),
        (FakePost(500, {"error": "boom"}), 502, "HTTP 500"),
        (FakePost(200, {"unexpected": True}), 502, "unexpected response"),
        (FakePost(200, {"message": {"content": "   "}}), 502, "empty answer"),
    ],
)
def test_ollama_error_branches(monkeypatch, ollama, fake_post, status, message):
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(Exception, match=message) as err:
        ollama.generate("s", "u")
    assert err.value.status_code == status


def test_factory_builds_the_configured_provider():
    assert isinstance(build_provider(Settings(_env_file=None)), OllamaProvider)
    gemini = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="k")
    assert isinstance(build_provider(gemini), GeminiProvider)


# --- Config, embeddings, vector store ------------------------------------------------------


def test_config_parsing(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test ,")
    monkeypatch.setenv("MIN_RELEVANCE_SCORE", "")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.min_relevance_score is None
    assert settings.data_dir == BACKEND_DIR / "data"  # relative paths anchor to backend/

    monkeypatch.setenv("MIN_RELEVANCE_SCORE", "0.35")
    assert Settings(_env_file=None).min_relevance_score == 0.35


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValidationError, match="CHUNK_OVERLAP"):
        Settings(_env_file=None, chunk_size=100, chunk_overlap=100)


def test_sentence_transformer_embedder_normalizes(monkeypatch):
    class FakeModel:
        def __init__(self, name):
            self.name = name

        def encode(self, texts, **kwargs):
            assert kwargs["normalize_embeddings"] is True
            return types.SimpleNamespace(tolist=lambda: [[0.6, 0.8] for _ in texts])

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeModel)
    )
    embedder = SentenceTransformerEmbedder("some-model")
    assert embedder.embed_documents(["a", "b"]) == [[0.6, 0.8], [0.6, 0.8]]
    assert embedder.embed_query("a") == [0.6, 0.8]


def test_vector_store_ignores_empty_chunk_list(tmp_path):
    store = VectorStore(tmp_path / "chroma")
    store.add_chunks("d", "a.pdf", [], [])
    assert store.count() == 0
    store.add_chunks("d", "a.pdf", [Chunk(page=1, index=0, text="x")], [[1.0, 0.0]])
    assert store.count() == 1
