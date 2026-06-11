"""API key generation, hashing, and parsing.

Key format: ``ctl_<prefix>_<secret>``.
- ``prefix`` is a public, non-secret lookup token stored in plaintext and
  indexed, so verification is an O(1) row fetch.
- ``secret`` is never stored. We store only ``sha256(salt + secret)`` plus the
  per-key ``salt``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

KEY_SCHEME = "ctl"


def hash_secret(secret: str, salt: str) -> str:
    return hashlib.sha256((salt + secret).encode("utf-8")).hexdigest()


@dataclass
class GeneratedKey:
    full_key: str  # shown to the user exactly once
    prefix: str
    key_hash: str
    salt: str


def generate_key() -> GeneratedKey:
    prefix = secrets.token_hex(8)   # 16 hex chars
    secret = secrets.token_hex(24)  # 48 hex chars
    salt = secrets.token_hex(16)
    return GeneratedKey(
        full_key=f"{KEY_SCHEME}_{prefix}_{secret}",
        prefix=prefix,
        key_hash=hash_secret(secret, salt),
        salt=salt,
    )


def parse_key(full_key: str) -> tuple[str, str] | None:
    """Return ``(prefix, secret)`` for a well-formed key, else ``None``."""
    if not full_key:
        return None
    parts = full_key.split("_")
    if len(parts) != 3 or parts[0] != KEY_SCHEME:
        return None
    _, prefix, secret = parts
    if not prefix or not secret:
        return None
    return prefix, secret


def verify_secret(secret: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(secret, salt), expected_hash)
