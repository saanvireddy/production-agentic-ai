"""Centralised settings. Every value can be overridden by an environment variable
(or a .env file locally, a ConfigMap/Secret in Kubernetes, Secrets Manager in AWS)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "production-agentic-ai"
    environment: Literal["local", "ci", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:8501"]
    # Startup tasks (disable in Kubernetes where a Job/init step owns them)
    auto_migrate: bool = True
    auto_seed: bool = True
    auto_ingest: bool = True

    # --- Auth ---
    jwt_secret: SecretStr = SecretStr("change-me-in-env")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    # Seeded on first start so the demo is usable; override in any real environment.
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("admin123")

    # --- PostgreSQL / pgvector ---
    database_url: str = "postgresql://agentic:agentic@localhost:5432/agentic"
    db_pool_min: int = 1
    db_pool_max: int = 10
    sql_statement_timeout_ms: int = 5000
    sql_max_rows: int = 100

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_per_minute: int = 30
    memory_max_turns: int = 10
    memory_ttl_seconds: int = 60 * 60 * 24
    cache_ttl_seconds: int = 300

    # --- LLM ---
    # "ollama" for real runs; "fake" gives a deterministic LLM for tests/CI.
    llm_provider: Literal["ollama", "fake"] = "ollama"
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    llm_temperature: float = 0.0
    llm_timeout_seconds: int = 120

    # --- Embeddings ---
    # "ollama" (nomic-embed-text) for real runs; "hash" is a dependency-free
    # hashed bag-of-words embedding used in tests/CI.
    embedding_provider: Literal["ollama", "hash"] = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # --- RAG ---
    documents_dir: str = "data/documents"
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 4
    # Chunks below this cosine similarity are not considered supporting evidence.
    retrieval_min_score: float = 0.35

    # --- Observability ---
    otel_enabled: bool = False
    otel_exporter_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "agentic-api"

    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")


@lru_cache
def get_settings() -> Settings:
    return Settings()
