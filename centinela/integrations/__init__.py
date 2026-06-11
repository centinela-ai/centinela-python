"""Automatic instrumentation for ``Centinela.wrap``.

Detection is by module name and duck typing so that none of the supported
frameworks (LangChain, OpenAI, Anthropic) need to be installed for the SDK to
import. Unsupported targets raise a clear, actionable error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import CentinelaError

if TYPE_CHECKING:
    from ..client import Centinela

_MANUAL_DOCS = (
    "https://github.com/centinela-ai/centinela-python#manual-instrumentation"
)


def _module_of(obj: Any) -> str:
    return (type(obj).__module__ or "").lower()


def _looks_like_openai(target: Any) -> bool:
    if "openai" not in _module_of(target):
        return False
    chat = getattr(target, "chat", None)
    return getattr(chat, "completions", None) is not None


def _looks_like_anthropic(target: Any) -> bool:
    if "anthropic" not in _module_of(target):
        return False
    messages = getattr(target, "messages", None)
    return getattr(messages, "create", None) is not None


def _looks_like_langchain(target: Any) -> bool:
    module = _module_of(target)
    if "langchain" in module or "langgraph" in module:
        return True
    # Generic LangChain Runnable duck type.
    return hasattr(target, "with_config") and hasattr(target, "invoke")


def wrap_target(client: "Centinela", target: Any) -> Any:
    """Detect the framework behind ``target`` and return an instrumented version."""
    if _looks_like_openai(target):
        from .openai import wrap_openai

        return wrap_openai(client, target)
    if _looks_like_anthropic(target):
        from .anthropic import wrap_anthropic

        return wrap_anthropic(client, target)
    if _looks_like_langchain(target):
        from .langchain import wrap_langchain

        return wrap_langchain(client, target)

    raise CentinelaError(
        f"Centinela could not auto-instrument an object of type "
        f"'{type(target).__module__}.{type(target).__name__}'. "
        f"Supported by wrap(): LangChain runnables, the OpenAI client, and the "
        f"Anthropic client. Use manual instrumentation instead "
        f"(c.trace(...) / t.log_action(...)): {_MANUAL_DOCS}"
    )
