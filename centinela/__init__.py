"""Centinela — flight recorder & firewall for AI agents."""

from .client import Centinela
from .errors import CentinelaError
from .events import EVENT_TYPES, Event
from .trace import Trace, current_trace

__version__ = "0.1.0"

__all__ = [
    "Centinela",
    "CentinelaError",
    "Event",
    "EVENT_TYPES",
    "Trace",
    "current_trace",
    "__version__",
]
