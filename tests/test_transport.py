from __future__ import annotations

import json

from centinela.transport import Transport


def test_stdout_transport_prints_json(capsys):
    transport = Transport("stdout", api_key=None, stdout=True, flush_interval=0.1)
    transport.enqueue({"trace_id": "t", "type": "tool_call"})
    transport.enqueue({"trace_id": "t", "type": "llm_call"})
    assert transport.flush(timeout=2.0)
    transport.close()

    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2
    assert json.loads(out[0])["type"] == "tool_call"
    assert json.loads(out[1])["type"] == "llm_call"


def test_send_failure_is_fail_open(caplog):
    # Unreachable endpoint: must not raise; should log a warning and continue.
    transport = Transport(
        "http://127.0.0.1:1", api_key="k", flush_interval=0.1, timeout=0.2
    )
    transport.enqueue({"trace_id": "t", "type": "tool_call"})
    # flush returns once the worker has processed (and failed to deliver) it
    transport.flush(timeout=3.0)
    transport.close()
    # The important assertion is simply that nothing above raised.


def test_enqueue_never_raises_after_close():
    transport = Transport("stdout", api_key=None, stdout=True, flush_interval=0.1)
    transport.close()
    # Enqueue after close must be a silent no-op, not an exception.
    transport.enqueue({"trace_id": "t", "type": "tool_call"})
