from __future__ import annotations

from types import SimpleNamespace

import pytest

from centinela import CentinelaError


# --- OpenAI-like fake -------------------------------------------------------

class _OACompletions:
    def create(self, **kwargs):
        return SimpleNamespace(usage=SimpleNamespace(total_tokens=42))


class _OAChat:
    def __init__(self):
        self.completions = _OACompletions()


class FakeOpenAI:
    def __init__(self):
        self.chat = _OAChat()


FakeOpenAI.__module__ = "openai"


# --- Anthropic-like fake ----------------------------------------------------

class _AnthMessages:
    def create(self, **kwargs):
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=10, output_tokens=5)
        )


class FakeAnthropic:
    def __init__(self):
        self.messages = _AnthMessages()


FakeAnthropic.__module__ = "anthropic"


# --- tests ------------------------------------------------------------------

def test_wrap_unknown_target_raises(captured):
    client, _ = captured
    with pytest.raises(CentinelaError) as exc:
        client.wrap(object())
    assert "manual instrumentation" in str(exc.value)


def test_wrap_openai_records_llm_call(captured):
    client, transport = captured
    oa = client.wrap(FakeOpenAI())
    oa.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

    assert len(transport.events) == 1
    event = transport.events[0]
    assert event["type"] == "llm_call"
    assert event["name"] == "openai.chat.completions.create"
    assert event["metadata"]["model"] == "gpt-4o"
    assert event["metadata"]["tokens"] == 42
    assert event["parent_span_id"] is None  # standalone trace outside c.trace


def test_wrap_openai_attaches_to_active_trace(captured):
    client, transport = captured
    oa = client.wrap(FakeOpenAI())
    with client.trace("run") as t:
        oa.chat.completions.create(model="gpt-4o", messages=[])
        t.log_action(type="tool_call", name="x")

    llm = transport.events[0]
    agent_end = transport.events[-1]
    assert llm["type"] == "llm_call"
    assert llm["trace_id"] == agent_end["trace_id"]
    assert llm["parent_span_id"] == agent_end["span_id"]


def test_wrap_openai_is_idempotent(captured):
    client, transport = captured
    oa = FakeOpenAI()
    client.wrap(oa)
    client.wrap(oa)  # second wrap must not double-patch
    oa.chat.completions.create(model="gpt-4o", messages=[])
    assert len(transport.events) == 1


def test_wrap_anthropic_records_token_sum(captured):
    client, transport = captured
    anth = client.wrap(FakeAnthropic())
    anth.messages.create(model="claude-sonnet-4", messages=[])

    event = transport.events[0]
    assert event["type"] == "llm_call"
    assert event["name"] == "anthropic.messages.create"
    assert event["metadata"]["model"] == "claude-sonnet-4"
    assert event["metadata"]["tokens"] == 15


def test_wrap_propagates_exceptions_but_still_records(captured):
    client, transport = captured

    class Boom(_OACompletions):
        def create(self, **kwargs):
            raise RuntimeError("upstream failure")

    oa = FakeOpenAI()
    oa.chat.completions = Boom()
    client.wrap(oa)

    with pytest.raises(RuntimeError):
        oa.chat.completions.create(model="gpt-4o", messages=[])

    assert len(transport.events) == 1
    assert transport.events[0]["status"] == "error"
