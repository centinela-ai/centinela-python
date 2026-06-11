"""Backend configuration, sourced from environment variables / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CENTINELA_", env_file=".env", extra="ignore")

    # SQLAlchemy URL for the application database.
    database_url: str = "postgresql+psycopg://centinela:centinela@localhost:5432/centinela_dev"

    # Max number of events accepted in a single POST /v1/events request.
    max_batch: int = 500

    # Reject requests whose body exceeds this many bytes (simple size guard).
    max_body_bytes: int = 8 * 1024 * 1024  # 8 MiB

    # Max number of traces returned by a single list query.
    max_list_limit: int = 1000


settings = Settings()
