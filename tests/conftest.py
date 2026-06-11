from __future__ import annotations

from typing import Any, Dict, List

import pytest

from centinela import Centinela


class CaptureTransport:
    """Stand-in transport that records enqueued event dicts in memory."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def enqueue(self, event: Dict[str, Any]) -> None:
        self.events.append(event)

    def flush(self, timeout: float = 5.0) -> bool:
        return True

    def close(self, timeout: float = 5.0) -> None:
        pass


@pytest.fixture
def captured():
    """A Centinela client whose transport captures events for assertions."""
    client = Centinela(project="test-project", endpoint="stdout")
    # Replace the real (stdout) transport with an in-memory capture.
    client._transport.close()
    transport = CaptureTransport()
    client._transport = transport
    return client, transport
