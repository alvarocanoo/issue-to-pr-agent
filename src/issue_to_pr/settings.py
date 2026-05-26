"""Runtime configuration loaded from environment / .env file.

Single source of truth for model IDs, sandbox limits, DB URL and secrets.
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

    anthropic_api_key: str = Field(default="", description="Anthropic API key.")

    planner_model: str = Field(default="claude-sonnet-4-6")
    executor_model: str = Field(default="claude-haiku-4-5-20251001")
    verifier_model: str = Field(default="claude-sonnet-4-6")

    database_url: str = Field(default="postgresql://itp:itp@localhost:5432/itp")

    sandbox_timeout_seconds: int = Field(default=1200, ge=60, le=3600)
    sandbox_memory_limit: str = Field(default="2g")

    langfuse_host: str = Field(default="")
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")


def get_settings() -> Settings:
    """Build a Settings instance. Cheap; cache only if it shows up in a profile."""
    return Settings()
