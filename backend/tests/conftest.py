from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.helpers import FakeLLM, HashingEmbedder


@pytest.fixture
def settings(tmp_path) -> Settings:
    # _env_file=None: tests must not pick up the developer's real .env.
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        max_upload_mb=1,
        ask_rate_limit_per_minute=0,
    )


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(settings, fake_llm) -> Iterator[TestClient]:
    app = create_app(settings=settings, embedder=HashingEmbedder(), llm=fake_llm)
    with TestClient(app) as test_client:  # "with" runs the startup/lifespan code
        yield test_client
