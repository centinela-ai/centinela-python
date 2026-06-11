"""Resolution of SDK configuration from explicit args and environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

#: Production default endpoint (placeholder domain, controlled by centinela-ai).
DEFAULT_ENDPOINT = "https://api.getcentinela.com"

#: Default endpoint when CENTINELA_ENV=dev and no endpoint is set explicitly.
DEV_ENDPOINT = "http://localhost:8000"

#: Special endpoint value that prints events to stdout instead of shipping them.
STDOUT_ENDPOINT = "stdout"

_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


@dataclass
class Config:
    api_key: Optional[str]
    endpoint: str
    disabled: bool

    @property
    def is_stdout(self) -> bool:
        return self.endpoint == STDOUT_ENDPOINT


def resolve_config(
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    disabled: Optional[bool] = None,
) -> Config:
    """Merge explicit arguments with environment variables.

    Precedence: explicit argument > environment variable > default.
    """
    resolved_key = api_key if api_key is not None else os.environ.get("CENTINELA_API_KEY")

    resolved_endpoint = endpoint if endpoint is not None else os.environ.get("CENTINELA_ENDPOINT")
    if not resolved_endpoint:
        is_dev = os.environ.get("CENTINELA_ENV", "").strip().lower() == "dev"
        resolved_endpoint = DEV_ENDPOINT if is_dev else DEFAULT_ENDPOINT
    resolved_endpoint = resolved_endpoint.rstrip("/") if resolved_endpoint != STDOUT_ENDPOINT else resolved_endpoint

    resolved_disabled = disabled if disabled is not None else _env_flag("CENTINELA_DISABLED")

    return Config(
        api_key=resolved_key,
        endpoint=resolved_endpoint,
        disabled=resolved_disabled,
    )
