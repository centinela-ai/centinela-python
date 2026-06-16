"""Manual instrumentation: the ``trace`` context manager and active-trace state.

The active trace is tracked with a :class:`contextvars.ContextVar`, so it works
correctly under threads and asyncio. Integrations (``wrap``) read the active
trace to attach their spans as children; if there is none they emit a
standalone single-span trace.
"""

from __future__ import annotations

import contextvars
import time
from typing import TYPE_CHECKING, Any, Optional

from .events import Event, new_id

if TYPE_CHECKING:
    from .client import Centinela

_current_trace: "contextvars.ContextVar[Optional[Trace]]" = contextvars.ContextVar(
    "centinela_current_trace", default=None
)


def current_trace() -> "Optional[Trace]":
    return _current_trace.get()


class Trace:
    """A single agent run. Acts as a context manager and span factory."""

    def __init__(
        self,
        client: "Centinela",
        name: str,
        ai_disclosed: Optional[bool] = None,
    ) -> None:
        self._client = client
        self.name = name
        self.trace_id = new_id()
        self.span_id = new_id()
        self._start: Optional[float] = None
        self._token: Optional[contextvars.Token] = None
        # Session-level AI-disclosure declaration (CTL-009). When set, every
        # action logged under this trace carries it inside metadata["_centinela"]
        # so the backend can group by session and verify disclosure was shown.
        # None means "not declared" → the control stays not_applicable.
        self._ai_disclosed = ai_disclosed

    def __enter__(self) -> "Trace":
        self._start = time.monotonic()
        self._token = _current_trace.set(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed_ms = (
            int((time.monotonic() - self._start) * 1000) if self._start else 0
        )
        metadata = {}
        status = "ok"
        if exc_type is not None:
            status = "error"
            metadata["error"] = {"type": exc_type.__name__, "message": str(exc)}
        self._client._emit(
            Event(
                trace_id=self.trace_id,
                span_id=self.span_id,
                parent_span_id=None,
                type="agent_end",
                name=self.name,
                duration_ms=elapsed_ms,
                status=status,
                metadata=metadata,
            )
        )
        if self._token is not None:
            _current_trace.reset(self._token)
            self._token = None
        return False  # never suppress the caller's exception

    def log_action(
        self,
        type: str,
        name: Optional[str] = None,
        input: Any = None,
        output: Any = None,
        status: str = "ok",
        duration_ms: int = 0,
        blocked: Optional[bool] = None,
        human_review: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        """Record a child action (span) under this trace.

        Any extra keyword arguments (e.g. ``model=``, ``tokens=``) are folded
        into the event ``metadata``.

        Compliance signals
        ------------------
        ``blocked`` and ``human_review`` are *formal* parameters (not free
        kwargs) that travel in a reserved sub-namespace, ``metadata["_centinela"]``,
        so they never collide with user metadata and the 12-key event contract
        stays frozen. Both default to ``None`` ("signal not emitted"), which the
        backend maps to ``not_applicable`` rather than a pass.

        - ``blocked``: the action was stopped by a guardrail before executing
          (CTL-003). ``True``/``False`` are both measured values; ``None`` means
          no gating signal was emitted.
        - ``human_review``: one of ``"approved"`` (human approved before
          execution — gates CTL-003 *and* satisfies CTL-007), ``"reviewed"``
          (post-hoc human oversight — satisfies CTL-007 only), or ``"none"``
          (explicitly no human involvement). ``None`` means not emitted.

        ``ai_disclosed`` is declared once per session on ``trace(...)`` and is
        stamped onto every action automatically — it is not a ``log_action``
        parameter.
        """
        centinela: dict[str, Any] = {}
        if blocked is not None:
            centinela["blocked"] = blocked
        if human_review is not None:
            centinela["human_review"] = human_review
        if self._ai_disclosed is not None:
            centinela["ai_disclosed"] = self._ai_disclosed
        if centinela:
            # Merge into any caller-supplied _centinela without clobbering it.
            metadata = {
                **metadata,
                "_centinela": {**metadata.get("_centinela", {}), **centinela},
            }
        self._client._emit(
            Event(
                trace_id=self.trace_id,
                span_id=new_id(),
                parent_span_id=self.span_id,
                type=type,
                name=name,
                input=input,
                output=output,
                status=status,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        )
