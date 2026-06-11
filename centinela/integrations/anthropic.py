"""Instrument an Anthropic SDK client by patching ``messages.create``."""

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
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    total = inp + out
    return total or None


def wrap_anthropic(client: "Centinela", anthropic_client: Any) -> Any:
    """Patch ``anthropic_client.messages.create`` to record llm_call spans.

    Returns the same client instance (patched in place). Idempotent.
    """
    messages = anthropic_client.messages
    if getattr(messages, _PATCHED_FLAG, False):
        return anthropic_client

    original = messages.create

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
                name="anthropic.messages.create",
                input=kwargs.get("messages"),
                status=status,
                duration_ms=int((time.monotonic() - start) * 1000),
                metadata=metadata,
            )

    messages.create = patched
    setattr(messages, _PATCHED_FLAG, True)
    return anthropic_client
