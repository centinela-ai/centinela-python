"""GET /v1/traces and GET /v1/traces/{trace_id} — multitenant trace queries.

Every query is filtered by the org id resolved from the API key. An optional
``org_id`` query param is honored only if it matches the authenticated org.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Integer, case, func, select
from sqlalchemy.orm import Session

from ..auth import require_org
from ..config import settings
from ..db import get_db
from ..models import Event
from ..schemas import TraceDetailResponse, TraceListResponse, TraceSummary

router = APIRouter(prefix="/v1", tags=["traces"])


def _enforce_org(authenticated: uuid.UUID, requested: Optional[uuid.UUID]) -> None:
    if requested is not None and requested != authenticated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="org_id does not match the authenticated API key.",
        )


@router.get("/traces", response_model=TraceListResponse)
def list_traces(
    org_id: Optional[uuid.UUID] = Query(default=None),
    from_: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    auth_org: uuid.UUID = Depends(require_org),
    db: Session = Depends(get_db),
) -> TraceListResponse:
    _enforce_org(auth_org, org_id)
    limit = min(limit, settings.max_list_limit)

    error_flag = case((Event.status == "error", 1), else_=0)
    stmt = (
        select(
            Event.trace_id,
            func.count().label("event_count"),
            func.sum(error_flag.cast(Integer)).label("error_count"),
            func.min(Event.timestamp).label("first_ts"),
            func.max(Event.timestamp).label("last_ts"),
        )
        .where(Event.org_id == auth_org)
        .group_by(Event.trace_id)
        .order_by(func.max(Event.timestamp).desc())
        .limit(limit)
        .offset(offset)
    )
    if from_ is not None:
        stmt = stmt.where(Event.timestamp >= from_)
    if to is not None:
        stmt = stmt.where(Event.timestamp <= to)

    traces = []
    for row in db.execute(stmt):
        duration_ms = int((row.last_ts - row.first_ts).total_seconds() * 1000)
        traces.append(
            TraceSummary(
                trace_id=row.trace_id,
                event_count=row.event_count,
                error_count=int(row.error_count or 0),
                duration_ms=duration_ms,
                first_timestamp=row.first_ts,
                last_timestamp=row.last_ts,
            )
        )

    return TraceListResponse(traces=traces, limit=limit, offset=offset)


@router.get("/traces/{trace_id}", response_model=TraceDetailResponse)
def get_trace(
    trace_id: str,
    auth_org: uuid.UUID = Depends(require_org),
    db: Session = Depends(get_db),
) -> TraceDetailResponse:
    stmt = (
        select(Event.payload)
        .where(Event.org_id == auth_org, Event.trace_id == trace_id)
        .order_by(Event.timestamp.asc())
    )
    payloads = [row.payload for row in db.execute(stmt)]
    if not payloads:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found."
        )
    return TraceDetailResponse(
        trace_id=trace_id, event_count=len(payloads), events=payloads
    )
