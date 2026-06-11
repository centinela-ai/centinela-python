from __future__ import annotations

import uuid

from ._helpers import make_event


def _auth(key):
    return {"X-Centinela-Key": key}


def test_org_cannot_read_another_orgs_trace(client, make_org_key):
    _, key_a = make_org_key(org_name="org-a", key_name="a")
    _, key_b = make_org_key(org_name="org-b", key_name="b")

    trace_id = str(uuid.uuid4())
    client.post("/v1/events", json=[make_event(trace_id=trace_id)], headers=_auth(key_a))

    # Org A sees its trace.
    assert client.get(f"/v1/traces/{trace_id}", headers=_auth(key_a)).status_code == 200
    # Org B must not — it does not exist in B's tenant.
    assert client.get(f"/v1/traces/{trace_id}", headers=_auth(key_b)).status_code == 404


def test_list_traces_is_scoped_to_org(client, make_org_key):
    _, key_a = make_org_key(org_name="org-a", key_name="a")
    _, key_b = make_org_key(org_name="org-b", key_name="b")

    client.post("/v1/events", json=[make_event() for _ in range(3)], headers=_auth(key_a))

    list_a = client.get("/v1/traces", headers=_auth(key_a)).json()
    list_b = client.get("/v1/traces", headers=_auth(key_b)).json()
    assert len(list_a["traces"]) == 3
    assert list_b["traces"] == []


def test_mismatched_org_id_param_forbidden(client, make_org_key):
    org_a, key_a = make_org_key(org_name="org-a", key_name="a")
    other_org = str(uuid.uuid4())
    # Passing a different org_id than the key's org is rejected.
    resp = client.get(f"/v1/traces?org_id={other_org}", headers=_auth(key_a))
    assert resp.status_code == 403
    # Passing the matching org_id is allowed.
    ok = client.get(f"/v1/traces?org_id={org_a}", headers=_auth(key_a))
    assert ok.status_code == 200
