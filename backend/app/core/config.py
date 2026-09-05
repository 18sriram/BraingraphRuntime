from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="BrainGraph Runtime")
    environment: str = Field(default="development")
    debug: bool = Field(default=False)
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password")
    sqlite_database_url: str = Field(default="sqlite:///./runtime.db")
    model_provider: Literal["openai", "anthropic", "gemini"] = Field(default="openai")
    model_timeout_seconds: float = Field(default=30.0, gt=0)
    model_max_retries: int = Field(default=2, ge=0)
    openai_model: str = Field(default="gpt-4o-mini")
    anthropic_model: str = Field(default="claude-3-5-haiku-latest")
    gemini_model: str = Field(default="gemini-1.5-flash")
    openai_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")
    project_root: str = Field(default=".")
    safety_network_enabled: bool = Field(default=False)
    safety_docker_image: str = Field(default="python:3.12-slim")
    safety_cpu_limit: float = Field(default=1.0, gt=0)
    safety_memory_limit_mb: int = Field(default=512, gt=0)
    safety_timeout_seconds: float = Field(default=30.0, gt=0)
    safety_audit_log: str = Field(default="./runtime-audit.jsonl")
    scheduler_state_file: str = Field(default="./scheduler-state.json")
    scheduler_poll_interval_seconds: float = Field(default=30.0, gt=0)
    git_auto_commit: bool = Field(default=False)
    git_commit_message: str = Field(default="chore: automatic agent checkpoint")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
