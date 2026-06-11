"""Instrument an OpenAI SDK client by patching ``chat.completions.create``."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ._common import emit_span

if TYPE_CHECKING:
    from ..client import Centinela

_PATCHED_FLAG = "_centinela_patched"


def _usage_tokens(response: Any) -> Any:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return getattr(usage, "total_tokens", None)


def wrap_openai(client: "Centinela", openai_client: Any) -> Any:
    """Patch ``openai_client.chat.completions.create`` to record llm_call spans.

    Returns the same client instance (patched in place). Idempotent.
    """
    completions = openai_client.chat.completions
    if getattr(completions, _PATCHED_FLAG, False):
        return openai_client

    original = completions.create

    def patched(*args: Any, **kwargs: Any) -> Any:
        start = time.monotonic()
        model = kwargs.get("model")
        response = None
        status = "ok"
        try:
            response = original(*args, **kwargs)
            return response
        except Exception:
            status = "error"
            raise
        finally:
            metadata = {"model": model}
            tokens = _usage_tokens(response)
            if tokens is not None:
                metadata["tokens"] = tokens
            emit_span(
                client,
                type="llm_call",
                name="openai.chat.completions.create",
                input=kwargs.get("messages"),
                status=status,
                duration_ms=int((time.monotonic() - start) * 1000),
                metadata=metadata,
            )

    completions.create = patched
    setattr(completions, _PATCHED_FLAG, True)
    return openai_client
