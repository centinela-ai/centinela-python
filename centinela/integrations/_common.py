"""Shared helpers for the auto-instrumentation wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from ..events import Event, new_id
from ..trace import current_trace

if TYPE_CHECKING:
    from ..client import Centinela


def emit_span(
    client: "Centinela",
    *,
    type: str,
    name: Optional[str] = None,
    input: Any = None,
    output: Any = None,
    status: str = "ok",
    duration_ms: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a span, attaching it to the active trace if there is one.

    When called outside any ``c.trace(...)`` block, the span becomes its own
    single-event trace (fresh ``trace_id``, no parent).
    """
    trace = current_trace()
    if trace is not None:
        trace_id = trace.trace_id
        parent_span_id = trace.span_id
    else:
        trace_id = new_id()
        parent_span_id = None

    client._emit(
        Event(
            trace_id=trace_id,
            span_id=new_id(),
            parent_span_id=parent_span_id,
            type=type,
            name=name,
            input=input,
            output=output,
            status=status,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
    )
