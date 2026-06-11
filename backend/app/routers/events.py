"""POST /v1/events — batch ingestion."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..auth import require_org
from ..config import settings
from ..db import get_db
from ..models import Event
from ..schemas import EventIn, IngestResponse, RejectedEvent

router = APIRouter(prefix="/v1", tags=["events"])


@router.post("/events", response_model=IngestResponse)
async def ingest_events(
    request: Request,
    org_id: uuid.UUID = Depends(require_org),
    db: Session = Depends(get_db),
) -> IngestResponse:
    body = await request.json()
    if not isinstance(body, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be a JSON array of events.",
        )
    if len(body) > settings.max_batch:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Batch too large: {len(body)} events (max {settings.max_batch}).",
        )

    rejected: list[RejectedEvent] = []
    rows: list[dict[str, Any]] = []

    for index, raw in enumerate(body):
        try:
            event = EventIn.model_validate(raw)
        except ValidationError as exc:
            rejected.append(RejectedEvent(index=index, error=_summarize(exc)))
            continue
        except Exception as exc:  # malformed item, not a dict, etc.
            rejected.append(RejectedEvent(index=index, error=str(exc)))
            continue

        rows.append(
            {
                "id": uuid.uuid4(),
                "org_id": org_id,
                "trace_id": event.trace_id,
                "span_id": event.span_id,
                "parent_span_id": event.parent_span_id,
                "project": event.project,
                "type": event.type,
                "name": event.name,
                "status": event.status,
                "duration_ms": event.duration_ms,
                "timestamp": event.timestamp,
                "payload": raw,
            }
        )

    if rows:
        db.execute(Event.__table__.insert(), rows)
        db.commit()

    return IngestResponse(accepted=len(rows), rejected=rejected)


def _summarize(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg')}" if loc else err.get("msg", "invalid"))
    return "; ".join(parts) or "validation error"
