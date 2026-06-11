from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from ._helpers import make_event


def _auth(key):
    return {"X-Centinela-Key": key}


def test_trace_detail_is_ordered_by_timestamp(client, make_org_key):
    _, key = make_org_key()
    trace_id = str(uuid.uuid4())
    base = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Send out of order; expect sorted-by-timestamp on read.
    events = [
        make_event(trace_id=trace_id, name="third", timestamp=(base + timedelta(seconds=3)).isoformat()),
        make_event(trace_id=trace_id, name="first", timestamp=base.isoformat()),
        make_event(trace_id=trace_id, name="second", timestamp=(base + timedelta(seconds=1)).isoformat()),
    ]
    client.post("/v1/events", json=events, headers=_auth(key))

    detail = client.get(f"/v1/traces/{trace_id}", headers=_auth(key)).json()
    names = [e["name"] for e in detail["events"]]
    assert names == ["first", "second", "third"]


def test_trace_summary_counts_and_errors(client, make_org_key):
    _, key = make_org_key()
    trace_id = str(uuid.uuid4())
    events = [
        make_event(trace_id=trace_id, status="ok"),
        make_event(trace_id=trace_id, status="ok"),
        make_event(trace_id=trace_id, status="error", type="error"),
    ]
    client.post("/v1/events", json=events, headers=_auth(key))

    listing = client.get("/v1/traces", headers=_auth(key)).json()
    assert len(listing["traces"]) == 1
    summary = listing["traces"][0]
    assert summary["trace_id"] == trace_id
    assert summary["event_count"] == 3
    assert summary["error_count"] == 1
    assert summary["duration_ms"] >= 0


def test_trace_list_pagination(client, make_org_key):
    _, key = make_org_key()
    # 5 distinct traces, one event each.
    for _ in range(5):
        client.post("/v1/events", json=[make_event()], headers=_auth(key))

    page1 = client.get("/v1/traces?limit=2&offset=0", headers=_auth(key)).json()
    page2 = client.get("/v1/traces?limit=2&offset=2", headers=_auth(key)).json()
    page3 = client.get("/v1/traces?limit=2&offset=4", headers=_auth(key)).json()

    assert len(page1["traces"]) == 2
    assert len(page2["traces"]) == 2
    assert len(page3["traces"]) == 1

    ids = {t["trace_id"] for t in page1["traces"] + page2["traces"] + page3["traces"]}
    assert len(ids) == 5  # no overlap across pages


def test_unknown_trace_returns_404(client, make_org_key):
    _, key = make_org_key()
    resp = client.get(f"/v1/traces/{uuid.uuid4()}", headers=_auth(key))
    assert resp.status_code == 404


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
