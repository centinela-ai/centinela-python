"""Tests for the v0.2 compliance signals carried in metadata["_centinela"].

These cover the additive instrumentation surface:
  - ``log_action(blocked=...)``            → CTL-003 (gating)
  - ``log_action(human_review=...)``       → CTL-003 (gate) + CTL-007 (oversight)
  - ``trace(name, ai_disclosed=...)``      → CTL-009 (per-session disclosure)

Design invariants asserted here:
  * Signals travel ONLY inside ``metadata["_centinela"]`` — never as new
    top-level event keys (the 12-key contract stays frozen).
  * ``None`` (the default) emits NO signal at all, so an un-instrumented call
    is byte-for-byte identical to today's behaviour (backward compatible).
  * User metadata and the reserved ``_centinela`` namespace coexist without
    collision.
"""

from __future__ import annotations

from centinela import Centinela
from centinela.events import EVENT_TYPES

EXPECTED_KEYS = [
    "trace_id", "span_id", "parent_span_id", "project", "timestamp", "type",
    "name", "input", "output", "metadata", "duration_ms", "status",
]


def _client_capturing(**kwargs):
    """A client whose transport captures enqueued event dicts in memory."""
    c = Centinela(project="p", endpoint="stdout", **kwargs)
    c._transport.close()
    captured: list = []
    c._transport = type(
        "T",
        (),
        {
            "enqueue": lambda self, e: captured.append(e),
            "flush": lambda self, t=5.0: True,
            "close": lambda self, t=5.0: None,
        },
    )()
    return c, captured


# --- backward compatibility ------------------------------------------------

def test_no_signals_emits_no_centinela_namespace():
    """An un-instrumented log_action must not introduce a _centinela key."""
    c, captured = _client_capturing()
    with c.trace("run") as t:
        t.log_action(type="tool_call", name="x", model="claude")
    action = captured[0]
    assert "_centinela" not in action["metadata"]
    assert action["metadata"] == {"model": "claude"}


def test_event_contract_keys_unchanged_with_signals():
    """Signals live inside metadata; the top-level key set must not grow."""
    c, captured = _client_capturing()
    with c.trace("run", ai_disclosed=True) as t:
        t.log_action(type="tool_call", name="x", blocked=True, human_review="approved")
    action = captured[0]
    assert list(action.keys()) == EXPECTED_KEYS
    assert action["type"] in EVENT_TYPES


# --- blocked ----------------------------------------------------------------

def test_blocked_true_lands_in_centinela():
    c, captured = _client_capturing()
    with c.trace("run") as t:
        t.log_action(type="tool_call", name="transfer", blocked=True)
    assert captured[0]["metadata"]["_centinela"] == {"blocked": True}


def test_blocked_false_is_a_measured_value():
    """blocked=False is an explicit measurement, not absence — it is emitted."""
    c, captured = _client_capturing()
    with c.trace("run") as t:
        t.log_action(type="tool_call", name="transfer", blocked=False)
    assert captured[0]["metadata"]["_centinela"] == {"blocked": False}


# --- human_review -----------------------------------------------------------

def test_human_review_approved():
    c, captured = _client_capturing()
    with c.trace("run") as t:
        t.log_action(type="tool_call", name="approve_loan", human_review="approved")
    assert captured[0]["metadata"]["_centinela"] == {"human_review": "approved"}


def test_human_review_reviewed():
    c, captured = _client_capturing()
    with c.trace("run") as t:
        t.log_action(type="tool_call", name="close_account", human_review="reviewed")
    assert captured[0]["metadata"]["_centinela"] == {"human_review": "reviewed"}


def test_blocked_and_human_review_combine():
    c, captured = _client_capturing()
    with c.trace("run") as t:
        t.log_action(
            type="tool_call", name="x", blocked=True, human_review="approved"
        )
    assert captured[0]["metadata"]["_centinela"] == {
        "blocked": True,
        "human_review": "approved",
    }


# --- ai_disclosed (trace-level) --------------------------------------------

def test_ai_disclosed_stamped_on_every_action():
    c, captured = _client_capturing()
    with c.trace("chat", ai_disclosed=True) as t:
        t.log_action(type="tool_call", name="a")
        t.log_action(type="tool_call", name="b")
    a, b = captured[0], captured[1]
    assert a["metadata"]["_centinela"]["ai_disclosed"] is True
    assert b["metadata"]["_centinela"]["ai_disclosed"] is True


def test_ai_disclosed_default_none_emits_nothing():
    c, captured = _client_capturing()
    with c.trace("chat") as t:
        t.log_action(type="tool_call", name="a")
    assert "_centinela" not in captured[0]["metadata"]


def test_ai_disclosed_false_is_measured():
    """Explicitly declaring no disclosure must be recorded (can fail CTL-009)."""
    c, captured = _client_capturing()
    with c.trace("chat", ai_disclosed=False) as t:
        t.log_action(type="tool_call", name="a")
    assert captured[0]["metadata"]["_centinela"]["ai_disclosed"] is False


# --- coexistence with user metadata ----------------------------------------

def test_user_metadata_and_centinela_coexist():
    c, captured = _client_capturing()
    with c.trace("run", ai_disclosed=True) as t:
        t.log_action(
            type="llm_call", name="x", model="claude", tokens=99, blocked=False
        )
    meta = captured[0]["metadata"]
    assert meta["model"] == "claude"
    assert meta["tokens"] == 99
    assert meta["_centinela"] == {"blocked": False, "ai_disclosed": True}


def test_caller_supplied_centinela_is_not_clobbered():
    """If a caller passes their own _centinela kwarg, formal signals merge in."""
    c, captured = _client_capturing()
    with c.trace("run") as t:
        t.log_action(
            type="tool_call", name="x", blocked=True, _centinela={"custom": 1}
        )
    assert captured[0]["metadata"]["_centinela"] == {"custom": 1, "blocked": True}
