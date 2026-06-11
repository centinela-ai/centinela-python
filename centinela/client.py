"""The public ``Centinela`` client."""

from __future__ import annotations

import atexit
import logging
from typing import Any, Optional

from .config import resolve_config
from .events import Event
from .trace import Trace
from .transport import Transport

logger = logging.getLogger("centinela")


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
        redact: bool = False,
        disabled: Optional[bool] = None,
        flush_interval: float = 2.0,
        max_batch: int = 20,
    ) -> None:
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
            if self.redact:
                payload["input"] = None
                payload["output"] = None
            self._transport.enqueue(payload)
        except Exception as exc:  # pragma: no cover - defensive, fail-open
            logger.warning("centinela: failed to emit event: %s", exc)
