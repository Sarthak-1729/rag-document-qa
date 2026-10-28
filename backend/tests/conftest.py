from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.helpers import HashingEmbedder


@pytest.fixture
def settings(tmp_path) -> Settings:
    # _env_file=None: tests must not pick up the developer's real .env.
    return Settings(_env_file=None, data_dir=tmp_path / "data", max_upload_mb=1)


@pytest.fixture
def client(settings) -> Iterator[TestClient]:
    app = create_app(settings=settings, embedder=HashingEmbedder())
    with TestClient(app) as test_client:  # "with" runs the startup/lifespan code
        yield test_client
