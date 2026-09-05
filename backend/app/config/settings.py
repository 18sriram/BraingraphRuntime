from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration for the local runtime infrastructure.

    These values are intentionally simple and infrastructure-focused. They are meant
    to support local bootstrapping, Docker connectivity, and environment isolation.
    """

    app_name: str = Field(default="BrainGraph Runtime")
    environment: Literal["development", "testing", "production"] = Field(default="development")
    debug: bool = Field(default=False)

    database_url: str = Field(default="sqlite:///./runtime.db")
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password")

    openai_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")
    model_provider: Literal["openai", "anthropic", "gemini", "ollama"] = Field(default="ollama")
    local_model_provider: Literal["ollama"] = Field(default="ollama")
    local_model: str = Field(default="qwen3:8b-instruct")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434")
    model_timeout_seconds: float = Field(default=30.0, gt=0)
    model_max_retries: int = Field(default=2, ge=0)
    openai_model: str = Field(default="gpt-4o-mini")
    anthropic_model: str = Field(default="claude-3-5-haiku-latest")
    gemini_model: str = Field(default="gemini-1.5-flash")
    project_root: str = Field(default=".")
    safety_network_enabled: bool = Field(default=False)
    safety_docker_image: str = Field(default="python:3.12-slim")
    safety_cpu_limit: float = Field(default=1.0, gt=0)
    safety_memory_limit_mb: int = Field(default=512, gt=0)
    safety_timeout_seconds: float = Field(default=30.0, gt=0)
    safety_audit_log: str = Field(default="./runtime-audit.jsonl")

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_prefix="",
        extra="ignore",
        protected_namespaces=("settings_",),
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings object for the runtime."""
    return Settings()
