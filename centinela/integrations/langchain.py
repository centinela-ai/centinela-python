"""Instrument LangChain runnables via a ``BaseCallbackHandler``.

``langchain`` is not a dependency of this package, so the handler class is
constructed lazily: we only import ``BaseCallbackHandler`` when the user
actually wraps a LangChain object.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from ..errors import CentinelaError
from ..events import Event, new_id

if TYPE_CHECKING:
    from ..client import Centinela


def _import_base_handler():
    try:
        from langchain_core.callbacks import BaseCallbackHandler  # type: ignore

        return BaseCallbackHandler
    except Exception:
        try:
            from langchain.callbacks.base import BaseCallbackHandler  # type: ignore

            return BaseCallbackHandler
        except Exception as exc:
            raise CentinelaError(
                "LangChain was detected but its callbacks could not be imported. "
                "Install 'langchain-core', or use manual instrumentation."
            ) from exc


def build_callback_handler(client: "Centinela"):
    """Return an instance of a Centinela LangChain callback handler."""
    base = _import_base_handler()

    class CentinelaCallbackHandler(base):  # type: ignore[misc, valid-type]
        """Maps LangChain run callbacks onto Centinela events.

        LangChain assigns each run a ``run_id`` and ``parent_run_id``. The
        root run (no parent) defines the trace; nested runs become child spans.
        """

        def __init__(self) -> None:
            super().__init__()
            self._client = client
            # run_id -> {trace_id, span_id, parent_span_id, start, name}
            self._runs: Dict[str, Dict[str, Any]] = {}

        # -- bookkeeping ---------------------------------------------------

        def _start(
            self,
            run_id: Any,
            parent_run_id: Any,
            name: Optional[str],
        ) -> None:
            run_key = str(run_id)
            parent = self._runs.get(str(parent_run_id)) if parent_run_id else None
            trace_id = parent["trace_id"] if parent else run_key
            parent_span_id = parent["span_id"] if parent else None
            self._runs[run_key] = {
                "trace_id": trace_id,
                "span_id": new_id(),
                "parent_span_id": parent_span_id,
                "start": time.monotonic(),
                "name": name,
            }

        def _finish(
            self,
            run_id: Any,
            type: str,
            output: Any = None,
            input: Any = None,
            status: str = "ok",
            metadata: Optional[Dict[str, Any]] = None,
        ) -> None:
            info = self._runs.pop(str(run_id), None)
            if info is None:
                return
            self._client._emit(
                Event(
                    trace_id=info["trace_id"],
                    span_id=info["span_id"],
                    parent_span_id=info["parent_span_id"],
                    type=type,
                    name=info["name"],
                    input=input,
                    output=output,
                    status=status,
                    duration_ms=int((time.monotonic() - info["start"]) * 1000),
                    metadata=metadata or {},
                )
            )

        # -- LLM -----------------------------------------------------------

        def on_llm_start(self, serialized, prompts, *, run_id=None, parent_run_id=None, **kwargs):
            name = (serialized or {}).get("name") if isinstance(serialized, dict) else None
            self._start(run_id, parent_run_id, name or "llm")
            info = self._runs.get(str(run_id))
            if info is not None:
                info["input"] = prompts

        def on_chat_model_start(self, serialized, messages, *, run_id=None, parent_run_id=None, **kwargs):
            name = (serialized or {}).get("name") if isinstance(serialized, dict) else None
            self._start(run_id, parent_run_id, name or "chat_model")
            info = self._runs.get(str(run_id))
            if info is not None:
                info["input"] = messages

        def on_llm_end(self, response, *, run_id=None, **kwargs):
            info = self._runs.get(str(run_id), {})
            self._finish(run_id, "llm_call", output=str(response)[:2000], input=info.get("input"))

        def on_llm_error(self, error, *, run_id=None, **kwargs):
            self._finish(run_id, "llm_call", status="error", metadata={"error": str(error)})

        # -- Tools ---------------------------------------------------------

        def on_tool_start(self, serialized, input_str, *, run_id=None, parent_run_id=None, **kwargs):
            name = (serialized or {}).get("name") if isinstance(serialized, dict) else None
            self._start(run_id, parent_run_id, name or "tool")
            info = self._runs.get(str(run_id))
            if info is not None:
                info["input"] = input_str

        def on_tool_end(self, output, *, run_id=None, **kwargs):
            info = self._runs.get(str(run_id), {})
            self._finish(run_id, "tool_call", output=str(output)[:2000], input=info.get("input"))

        def on_tool_error(self, error, *, run_id=None, **kwargs):
            self._finish(run_id, "tool_call", status="error", metadata={"error": str(error)})

        # -- Chains / agents ----------------------------------------------

        def on_chain_start(self, serialized, inputs, *, run_id=None, parent_run_id=None, **kwargs):
            name = (serialized or {}).get("name") if isinstance(serialized, dict) else None
            self._start(run_id, parent_run_id, name or "chain")

        def on_chain_end(self, outputs, *, run_id=None, **kwargs):
            self._finish(run_id, "agent_end")

        def on_chain_error(self, error, *, run_id=None, **kwargs):
            self._finish(run_id, "agent_end", status="error", metadata={"error": str(error)})

    return CentinelaCallbackHandler()


def wrap_langchain(client: "Centinela", runnable: Any) -> Any:
    """Attach a Centinela callback handler to a LangChain runnable."""
    handler = build_callback_handler(client)
    if hasattr(runnable, "with_config"):
        return runnable.with_config({"callbacks": [handler]})
    # Fallback for older callback-manager style objects.
    callbacks = getattr(runnable, "callbacks", None)
    if isinstance(callbacks, list):
        callbacks.append(handler)
    else:
        runnable.callbacks = [handler]
    return runnable
