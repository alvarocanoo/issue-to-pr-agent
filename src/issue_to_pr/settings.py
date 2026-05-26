"""Runtime configuration loaded from environment / .env file.

Single source of truth for model IDs, sandbox limits and secrets.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Groq API
    groq_api_key: str = Field(default="", description="Groq API key.")
    groq_base_url: str = Field(default="https://api.groq.com")

    # Model routing — see ADR-004
    planner_model: str = Field(default="openai/gpt-oss-120b")
    executor_model: str = Field(default="openai/gpt-oss-20b")
    verifier_model: str = Field(default="openai/gpt-oss-120b")

    # Postgres — used from Week 3 onwards (pgsql-portable on Windows, see docs/POSTGRES.md)
    database_url: str = Field(default="postgresql://itp:itp@localhost:5432/itp")

    # Sandbox — see ADR-003
    sandbox_timeout_seconds: int = Field(default=1200, ge=60, le=3600)
    sandbox_memory_limit: str = Field(default="2g")

    # Langfuse — wired in Week 3
    langfuse_host: str = Field(default="")
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")


def get_settings() -> Settings:
    """Build a Settings instance. Cheap; cache only if it shows up in a profile."""
    return Settings()
