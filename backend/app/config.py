"""Application settings, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # The .env lives at the repo root; a missing file is simply ignored.
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: Literal["ollama", "gemini"] = "ollama"
    llm_max_tokens: int = Field(default=1024, gt=0, le=8192)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_num_ctx: int = Field(default=8192, ge=2048)

    # SecretStr keeps the key out of logs, reprs and error messages.
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_thinking_level: Literal["", "minimal", "low", "medium", "high"] = "minimal"

    ask_top_k: int = Field(default=5, ge=1, le=20)
    # Refuse without calling the LLM when the best chunk scores below this cosine similarity.
    # Off (None) until it is tuned on the eval set in Phase 6.
    min_relevance_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    # Requests per client IP per minute on /ask; 0 disables the limit.
    ask_rate_limit_per_minute: int = Field(default=10, ge=0)

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    data_dir: Path = Path("data")
    max_upload_mb: int = Field(default=20, gt=0, le=200)
    max_files_per_upload: int = Field(default=10, gt=0)

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # ~800 chars is ~200 tokens: safely under MiniLM's 256-token input limit.
    chunk_size: int = Field(default=800, gt=0)
    chunk_overlap: int = Field(default=150, ge=0)

    @model_validator(mode="after")
    def check_overlap(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.llm_provider == "gemini" and not (
            self.gemini_api_key and self.gemini_api_key.get_secret_value().strip()
        ):
            raise ValueError("LLM_PROVIDER=gemini requires GEMINI_API_KEY")
        return self

    @field_validator("min_relevance_score", mode="before")
    @classmethod
    def empty_threshold_is_off(cls, value: object) -> object:
        # MIN_RELEVANCE_SCORE= (empty) in .env means "off".
        return None if value == "" else value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        # Allow CORS_ORIGINS="http://a,http://b" in the environment.
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("data_dir")
    @classmethod
    def resolve_data_dir(cls, value: Path) -> Path:
        # Relative paths are anchored to backend/ so the cwd doesn't matter.
        return value if value.is_absolute() else BACKEND_DIR / value

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma_db"

    @property
    def registry_path(self) -> Path:
        return self.data_dir / "documents.json"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
