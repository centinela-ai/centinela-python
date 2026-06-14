"""The public ``Centinela`` client."""

from __future__ import annotations

import atexit
import logging
from typing import Any, List, Optional, Set, Union

from .config import resolve_config
from .events import Event
from .trace import Trace
from .transport import Transport

logger = logging.getLogger("centinela")

#: Placeholder written in place of a redacted field value. A visible sentinel
#: (rather than ``None``) keeps the audit trail honest: the dashboard shows that
#: something WAS there and was deliberately masked, not merely absent.
_REDACTED = "[REDACTED]"


def _redact_fields(value: Any, keys: Set[str]) -> Any:
    """Return a copy of ``value`` with any dict key in ``keys`` masked.

    Recurses through nested dicts and lists/tuples so a field is masked at any
    depth - this matters because real payloads are nested (e.g. the Anthropic
    ``messages`` input is a list of ``{"role", "content"}`` dicts, and tool
    inputs/outputs can be arbitrarily nested).

    Never mutates the input. The caller's original objects (which may be the very
    lists/dicts they passed to their LLM) are left untouched; a redacted copy is
    built instead.
    """
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k in keys else _redact_fields(v, keys))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_fields(item, keys) for item in value]
    return value


class Centinela:
    """Entry point for instrumenting an AI agent.

    Example::

        c = Centinela(api_key="ctl_...", project="mi-agente")
        agent = c.wrap(agent)              # automatic
        with c.trace("procesar_pedido") as t:   # manual
            t.log_action(type="tool_call", name="enviar_email", input={...})
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        project: Optional[str] = None,
        endpoint: Optional[str] = None,
        redact: Union[bool, List[str]] = False,
        disabled: Optional[bool] = None,
        flush_interval: float = 2.0,
        max_batch: int = 20,
    ) -> None:
        """``redact`` controls what leaves the host process:

        - ``False`` (default): payloads are shipped as-is.
        - ``True``: ``input`` and ``output`` are dropped entirely - only
          structure, names, timing and status are shipped.
        - ``list[str]``: the named dict keys are masked (recursively, at any
          depth) inside ``input``/``output``; everything else is shipped. Use
          this to strip known sensitive fields (e.g. ``["email", "ssn"]``) while
          keeping the rest of the trace useful.

        Note: field redaction masks the *value of named keys* in structured
        payloads. It does not scrub sensitive substrings embedded in free text
        (e.g. an email mentioned mid-sentence in a prompt). For that, use
        ``redact=True``.
        """
        config = resolve_config(api_key=api_key, endpoint=endpoint, disabled=disabled)
        self.project = project
        self.api_key = config.api_key
        self.endpoint = config.endpoint
        self.redact = redact
        self.disabled = config.disabled

        self._transport: Optional[Transport] = None
        if not self.disabled:
            self._transport = Transport(
                config.endpoint,
                config.api_key,
                max_batch=max_batch,
                flush_interval=flush_interval,
                stdout=config.is_stdout,
            )
            atexit.register(self.close)

    # -- public API --------------------------------------------------------

    def trace(self, name: str) -> Trace:
        """Open a trace (agent run) as a context manager."""
        return Trace(self, name)

    def wrap(self, target: Any) -> Any:
        """Automatically instrument a supported agent or LLM client.

        Supports LangChain runnables and the OpenAI / Anthropic SDK clients.
        Unrecognized objects raise :class:`CentinelaError` with a pointer to
        manual instrumentation.
        """
        from .integrations import wrap_target

        return wrap_target(self, target)

    def flush(self, timeout: float = 5.0) -> bool:
        """Block until queued events are delivered (or ``timeout`` elapses)."""
        if self._transport is None:
            return True
        return self._transport.flush(timeout)

    def close(self) -> None:
        """Flush and shut down the background delivery thread."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    # -- internal ----------------------------------------------------------

    def _emit(self, event: Event) -> None:
        """Stamp, optionally redact, and enqueue an event. Never raises."""
        try:
            if self.disabled or self._transport is None:
                return
            event.project = self.project
            payload = event.to_dict()
            if self.redact is True:
                # Full redaction: drop payloads entirely.
                payload["input"] = None
                payload["output"] = None
            elif self.redact:
                # Field-level redaction: mask named keys, keep the rest.
                keys = set(self.redact)
                payload["input"] = _redact_fields(payload["input"], keys)
                payload["output"] = _redact_fields(payload["output"], keys)
            self._transport.enqueue(payload)
        except Exception as exc:  # pragma: no cover - defensive, fail-open
            logger.warning("centinela: failed to emit event: %s", exc)
