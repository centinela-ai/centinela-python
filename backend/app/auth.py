"""Authentication: resolve the X-Centinela-Key header to an org id."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ApiKey
from .security import parse_key, verify_secret

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing API key",
    headers={"WWW-Authenticate": "X-Centinela-Key"},
)


def require_org(
    x_centinela_key: Optional[str] = Header(default=None, alias="X-Centinela-Key"),
    db: Session = Depends(get_db),
) -> uuid.UUID:
    """Return the org id for a valid, non-revoked API key, else raise 401."""
    parsed = parse_key(x_centinela_key or "")
    if parsed is None:
        raise _UNAUTHORIZED
    prefix, secret = parsed

    row = db.execute(
        select(ApiKey).where(ApiKey.key_prefix == prefix)
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise _UNAUTHORIZED
    if not verify_secret(secret, row.salt, row.key_hash):
        raise _UNAUTHORIZED

    return row.org_id
