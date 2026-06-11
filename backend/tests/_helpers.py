"""Shared test helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def make_event(trace_id=None, **overrides):
    """Build a valid SDK-shaped event dict, overridable per field."""
    event = {
        "trace_id": trace_id or str(uuid.uuid4()),
        "span_id": str(uuid.uuid4()),
        "parent_span_id": None,
        "project": "test-project",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "tool_call",
        "name": "do_thing",
        "input": {"x": 1},
        "output": {"ok": True},
        "metadata": {},
        "duration_ms": 5,
        "status": "ok",
    }
    event.update(overrides)
    return event
