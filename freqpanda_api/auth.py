"""API-key authentication.

Deliberately not a full user system (out of scope for phase 5), but shaped
so multi-user is an additive change later: every authenticated request
resolves to a `principal` string (the sha256 hex digest of the presented
key, never the raw key), which every row this API writes stores as
`created_by`. A future upgrade to real user accounts replaces
`require_api_key`'s body with a DB/session lookup that returns a user id
instead of a key hash -- every router, repository, and table already treats
`created_by` as an opaque owner identifier, so nothing else has to change.
"""
from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException, status

from .config import get_settings


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """FastAPI dependency: validates `X-API-Key` against the configured
    `API_KEYS` list and returns the caller's principal (key hash) for use
    as `created_by`. Raises 401 if missing/invalid, and 500 if the server
    has no keys configured at all (a misconfiguration, not a client error).
    """
    settings = get_settings()
    if not settings.api_keys:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No API keys configured on the server (set API_KEYS).",
        )
    for configured_key in settings.api_keys:
        if hmac.compare_digest(configured_key, x_api_key):
            return _hash_key(configured_key)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
