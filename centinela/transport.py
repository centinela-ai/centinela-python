"""Asynchronous, non-blocking, fail-open event delivery.

Events are placed on an in-memory queue and shipped from a background daemon
thread that flushes every ``flush_interval`` seconds or once ``max_batch``
events have accumulated, whichever comes first.

Fail-open is the core invariant: nothing here may raise into the caller, and a
backend that is slow, erroring, or unreachable must never stall or crash the
host agent. Failures are logged at warning level and the events are dropped.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("centinela")

_SENTINEL = object()

# Cap the queue so a misbehaving/blocked backend can never grow memory without
# bound. When full, new events are dropped (fail-open) rather than blocking.
_MAX_QUEUE = 10_000


class Transport:
    def __init__(
        self,
        endpoint: str,
        api_key: Optional[str],
        *,
        max_batch: int = 20,
        flush_interval: float = 2.0,
        stdout: bool = False,
        timeout: float = 5.0,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._max_batch = max(1, max_batch)
        self._flush_interval = max(0.05, flush_interval)
        self._stdout = stdout
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=_MAX_QUEUE)
        self._client: Optional[httpx.Client] = None
        if not self._stdout:
            self._client = httpx.Client(timeout=timeout)
        self._closed = False
        self._thread = threading.Thread(
            target=self._run, name="centinela-flush", daemon=True
        )
        self._thread.start()

    # -- producer side -----------------------------------------------------

    def enqueue(self, event: Dict[str, Any]) -> None:
        """Queue an event for delivery. Never blocks, never raises."""
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("centinela: event queue full, dropping event")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("centinela: failed to enqueue event: %s", exc)

    # -- consumer side -----------------------------------------------------

    def _run(self) -> None:
        while True:
            batch, stop = self._collect()
            if batch:
                self._send(batch)
                for _ in batch:
                    self._queue.task_done()
            if stop:
                self._queue.task_done()  # account for the sentinel
                break

    def _collect(self):
        batch: List[Dict[str, Any]] = []
        deadline = time.monotonic() + self._flush_interval
        stop = False
        while len(batch) < self._max_batch:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                break
            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                break
            if item is _SENTINEL:
                stop = True
                break
            batch.append(item)
        return batch, stop

    def _send(self, batch: List[Dict[str, Any]]) -> None:
        if self._stdout:
            for event in batch:
                try:
                    print(json.dumps(event, default=str))
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("centinela: failed to print event: %s", exc)
            return
        try:
            response = self._client.post(  # type: ignore[union-attr]
                self._endpoint + "/v1/events",
                json=batch,
                headers={"X-Centinela-Key": self._api_key or ""},
            )
            if response.status_code >= 400:
                logger.warning(
                    "centinela: backend returned %s for %d events",
                    response.status_code,
                    len(batch),
                )
        except Exception as exc:
            # Fail-open: never propagate a delivery failure to the host agent.
            logger.warning(
                "centinela: failed to deliver %d events: %s", len(batch), exc
            )

    # -- lifecycle ---------------------------------------------------------

    def flush(self, timeout: float = 5.0) -> bool:
        """Block until queued events have been processed or ``timeout`` elapses.

        Returns ``True`` if the queue drained in time, ``False`` otherwise.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return self._queue.unfinished_tasks == 0

    def close(self, timeout: float = 5.0) -> None:
        """Drain remaining events and stop the background thread."""
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait(_SENTINEL)
        except queue.Full:
            # Make room for the sentinel so the worker can shut down.
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                self._queue.put_nowait(_SENTINEL)
            except Exception:  # pragma: no cover - defensive
                pass
        self._thread.join(timeout=timeout)
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # pragma: no cover - defensive
                pass
