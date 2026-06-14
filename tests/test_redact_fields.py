"""Tests for field-level redaction (``redact=[...]``).

These cover the new behaviour without touching the existing suite. The full-
redaction path (``redact=True``) keeps its original test in
``test_config_and_client.py``; one assertion is duplicated here only to lock in
that ``True`` and a field list remain distinct behaviours.
"""

from __future__ import annotations

from centinela import Centinela


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


def test_redact_list_masks_nested_dict_key():
    c, captured = _client_capturing(redact=["email"])
    with c.trace("run") as t:
        t.log_action(
            type="tool_call",
            name="send",
            input={"to": {"email": "a@b.com", "name": "Ana"}},
        )
    action = captured[0]
    assert action["input"]["to"]["email"] == "[REDACTED]"
    assert action["input"]["to"]["name"] == "Ana"  # unnamed key survives


def test_redact_list_masks_key_inside_list_of_dicts():
    # Mirrors the real Anthropic ``messages`` payload shape.
    c, captured = _client_capturing(redact=["content"])
    with c.trace("run") as t:
        t.log_action(
            type="llm_call",
            name="anthropic.messages.create",
            input=[{"role": "user", "content": "informacion confidencial"}],
        )
    action = captured[0]
    assert action["input"][0]["content"] == "[REDACTED]"
    assert action["input"][0]["role"] == "user"


def test_unnamed_keys_survive():
    c, captured = _client_capturing(redact=["ssn"])
    with c.trace("run") as t:
        t.log_action(
            type="tool_call",
            name="x",
            input={"amount": 100, "ssn": "123-45-6789"},
        )
    action = captured[0]
    assert action["input"]["amount"] == 100
    assert action["input"]["ssn"] == "[REDACTED]"


def test_empty_list_redacts_nothing():
    c, captured = _client_capturing(redact=[])
    with c.trace("run") as t:
        t.log_action(type="tool_call", name="x", input={"ssn": "secret"})
    assert captured[0]["input"]["ssn"] == "secret"


def test_redact_true_still_nulls_everything():
    c, captured = _client_capturing(redact=True)
    with c.trace("run") as t:
        t.log_action(type="tool_call", name="x", input={"a": 1}, output={"b": 2})
    assert captured[0]["input"] is None
    assert captured[0]["output"] is None


def test_redaction_does_not_mutate_caller_data():
    """The caller's original object (e.g. the list passed to their LLM) must
    never be altered by redaction - we ship a copy, they keep the original."""
    original = [{"role": "user", "content": "informacion confidencial"}]
    c, captured = _client_capturing(redact=["content"])
    with c.trace("run") as t:
        t.log_action(type="llm_call", name="x", input=original)
    assert original[0]["content"] == "informacion confidencial"  # intact
    assert captured[0]["input"][0]["content"] == "[REDACTED]"  # copy masked
