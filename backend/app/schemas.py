"""Pydantic schemas. ``EventIn`` mirrors the SDK event contract
(see ``centinela/events.py``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal["tool_call", "llm_call", "agent_start", "agent_end", "error"]


class EventIn(BaseModel):
    """A single ingested event. Unknown extra keys are ignored, not rejected."""

    model_config = ConfigDict(extra="ignore")

    trace_id: str
    span_id: str
    type: EventType
    timestamp: datetime
    parent_span_id: Optional[str] = None
    project: Optional[str] = None
    name: Optional[str] = None
    input: Any = None
    output: Any = None
    metadata: dict = Field(default_factory=dict)
    duration_ms: int = 0
    status: str = "ok"


class RejectedEvent(BaseModel):
    index: int
    error: str


class IngestResponse(BaseModel):
    accepted: int
    rejected: list[RejectedEvent] = Field(default_factory=list)


class TraceSummary(BaseModel):
    trace_id: str
    event_count: int
    error_count: int
    duration_ms: int
    first_timestamp: datetime
    last_timestamp: datetime


class TraceListResponse(BaseModel):
    traces: list[TraceSummary]
    limit: int
    offset: int


class TraceDetailResponse(BaseModel):
    trace_id: str
    event_count: int
    events: list[dict]
