from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration; secrets are never serialized into research state."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ORG_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "OpenResearchGraph"
    database_url: str = "sqlite:///./data/openresearchgraph.db"
    allowed_origins: str = "http://localhost:8000"
    max_search_rounds: int = Field(default=3, ge=1, le=8)
    max_sql_rows: int = Field(default=500, ge=1, le=10_000)
    sql_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    python_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    knowledge_dir: str = "./data/knowledge"
    web_search_base_url: str | None = None
    web_search_api_key: str | None = None
    memory_backend: str = "local"
    postgres_dsn: str | None = None
    milvus_uri: str | None = None
    milvus_token: str | None = None
    milvus_collection: str = "openresearchgraph_memory"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    log_level: str = "INFO"

    @property
    def database_path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("The current release supports sqlite:/// database URLs")
        value = self.database_url.removeprefix(prefix)
        return Path(value).expanduser().resolve()

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def knowledge_path(self) -> Path:
        return Path(self.knowledge_dir).expanduser().resolve()

    @property
    def use_remote_llm(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @field_validator("memory_backend")
    @classmethod
    def validate_memory_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"local", "postgres_milvus"}:
            raise ValueError("memory_backend must be local or postgres_milvus")
        return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
