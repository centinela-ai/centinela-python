"""The standard Centinela event and its serialization.

The JSON shape produced by :meth:`Event.to_dict` is the contract the backend
depends on. Keep field names and the ``type`` enum stable.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

#: Allowed values for ``Event.type``.
EVENT_TYPES = frozenset(
    {"tool_call", "llm_call", "agent_start", "agent_end", "error"}
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Event:
    trace_id: str
    span_id: str
    type: str
    parent_span_id: Optional[str] = None
    project: Optional[str] = None
    timestamp: str = field(default_factory=_now_iso)
    name: Optional[str] = None
    input: Any = None
    output: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    status: str = "ok"

    def to_dict(self) -> "OrderedDict[str, Any]":
        """Serialize to the standard event JSON shape (stable field order)."""
        return OrderedDict(
            [
                ("trace_id", self.trace_id),
                ("span_id", self.span_id),
                ("parent_span_id", self.parent_span_id),
                ("project", self.project),
                ("timestamp", self.timestamp),
                ("type", self.type),
                ("name", self.name),
                ("input", self.input),
                ("output", self.output),
                ("metadata", self.metadata),
                ("duration_ms", self.duration_ms),
                ("status", self.status),
            ]
        )
