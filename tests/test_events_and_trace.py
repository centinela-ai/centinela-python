from __future__ import annotations

import pytest

from centinela.events import EVENT_TYPES

EXPECTED_KEYS = [
    "trace_id",
    "span_id",
    "parent_span_id",
    "project",
    "timestamp",
    "type",
    "name",
    "input",
    "output",
    "metadata",
    "duration_ms",
    "status",
]


def test_event_contract_shape(captured):
    client, transport = captured
    with client.trace("procesar_pedido") as t:
        t.log_action(type="tool_call", name="enviar_email", input={"to": "a@b.c"})

    # one child action + the agent_end for the trace
    assert len(transport.events) == 2
    action = transport.events[0]

    assert list(action.keys()) == EXPECTED_KEYS
    assert action["type"] in EVENT_TYPES
    assert action["project"] == "test-project"
    assert action["type"] == "tool_call"
    assert action["name"] == "enviar_email"
    assert action["input"] == {"to": "a@b.c"}
    assert action["status"] == "ok"


def test_trace_parenting_and_ids(captured):
    client, transport = captured
    with client.trace("run") as t:
        t.log_action(type="tool_call", name="x")
        t.log_action(type="llm_call", name="y")

    action_x, action_y, agent_end = transport.events
    assert agent_end["type"] == "agent_end"
    assert agent_end["parent_span_id"] is None

    # all share the trace id; actions parent to the trace root span
    assert action_x["trace_id"] == agent_end["trace_id"]
    assert action_y["trace_id"] == agent_end["trace_id"]
    assert action_x["parent_span_id"] == agent_end["span_id"]
    assert action_y["parent_span_id"] == agent_end["span_id"]
    assert action_x["span_id"] != action_y["span_id"]


def test_log_action_extra_kwargs_go_to_metadata(captured):
    client, transport = captured
    with client.trace("run") as t:
        t.log_action(type="llm_call", model="claude-sonnet-4", tokens=1234)

    action = transport.events[0]
    assert action["metadata"] == {"model": "claude-sonnet-4", "tokens": 1234}


def test_trace_records_error_and_reraises(captured):
    client, transport = captured
    with pytest.raises(ValueError):
        with client.trace("boom"):
            raise ValueError("kaboom")

    assert len(transport.events) == 1
    end = transport.events[0]
    assert end["type"] == "agent_end"
    assert end["status"] == "error"
    assert end["metadata"]["error"]["type"] == "ValueError"
    assert end["metadata"]["error"]["message"] == "kaboom"


def test_duration_is_recorded(captured):
    client, transport = captured
    with client.trace("run"):
        pass
    assert transport.events[0]["duration_ms"] >= 0
