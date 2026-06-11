from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ApiKey

from ._helpers import make_event


def test_missing_key_is_unauthorized(client):
    resp = client.post("/v1/events", json=[make_event()])
    assert resp.status_code == 401


def test_malformed_key_is_unauthorized(client, make_org_key):
    make_org_key()
    resp = client.post(
        "/v1/events", json=[make_event()], headers={"X-Centinela-Key": "garbage"}
    )
    assert resp.status_code == 401


def test_wrong_secret_is_unauthorized(client, make_org_key):
    _, key = make_org_key()
    # Keep the valid prefix but corrupt the secret portion.
    prefix = key.split("_")[1]
    forged = f"ctl_{prefix}_{'0' * 48}"
    resp = client.post(
        "/v1/events", json=[make_event()], headers={"X-Centinela-Key": forged}
    )
    assert resp.status_code == 401


def test_revoked_key_is_unauthorized(client, make_org_key):
    _, key = make_org_key()
    prefix = key.split("_")[1]
    with SessionLocal() as db:
        row = db.execute(
            select(ApiKey).where(ApiKey.key_prefix == prefix)
        ).scalar_one()
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()

    resp = client.post(
        "/v1/events", json=[make_event()], headers={"X-Centinela-Key": key}
    )
    assert resp.status_code == 401
