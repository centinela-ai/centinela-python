from __future__ import annotations

import uuid

from ._helpers import make_event


def _auth(key):
    return {"X-Centinela-Key": key}


def test_valid_batch_is_accepted(client, make_org_key):
    _, key = make_org_key()
    trace_id = str(uuid.uuid4())
    events = [make_event(trace_id=trace_id) for _ in range(5)]

    resp = client.post("/v1/events", json=events, headers=_auth(key))
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] == 5
    assert body["rejected"] == []


def test_partially_invalid_batch_keeps_valid_events(client, make_org_key):
    _, key = make_org_key()
    good = make_event()
    bad_type = make_event()
    bad_type["type"] = "not_a_real_type"
    missing_field = make_event()
    del missing_field["trace_id"]

    resp = client.post(
        "/v1/events", json=[good, bad_type, missing_field], headers=_auth(key)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] == 1
    rejected_indices = {r["index"] for r in body["rejected"]}
    assert rejected_indices == {1, 2}
    # error messages are present and reference the offending field
    assert all(r["error"] for r in body["rejected"])


def test_non_array_body_rejected(client, make_org_key):
    _, key = make_org_key()
    resp = client.post("/v1/events", json={"not": "a list"}, headers=_auth(key))
    assert resp.status_code == 400


def test_batch_over_limit_rejected(client, make_org_key):
    _, key = make_org_key()
    events = [make_event() for _ in range(501)]
    resp = client.post("/v1/events", json=events, headers=_auth(key))
    assert resp.status_code == 413


def test_ingested_event_is_queryable(client, make_org_key):
    _, key = make_org_key()
    trace_id = str(uuid.uuid4())
    client.post("/v1/events", json=[make_event(trace_id=trace_id)], headers=_auth(key))

    resp = client.get(f"/v1/traces/{trace_id}", headers=_auth(key))
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["event_count"] == 1
    assert detail["events"][0]["trace_id"] == trace_id
