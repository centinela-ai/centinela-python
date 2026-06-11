"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from .config import settings
from .routers import events, health, traces

app = FastAPI(title="Centinela Backend", version="0.1.0")


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """Simple request-size guard (the only rate limiting in this phase)."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > settings.max_body_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request body too large."},
                )
        except ValueError:
            pass
    return await call_next(request)


app.include_router(health.router)
app.include_router(events.router)
app.include_router(traces.router)
