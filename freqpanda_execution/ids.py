"""Prefixed, application-generated ids -- same scheme as `freqpanda_api.ids`
(plain `uuid4` hex strings, not Postgres-generated uuids, so nothing here
depends on a Postgres extension being enabled). Kept as a tiny local copy
rather than a cross-import so `freqpanda_execution` has no dependency on
`freqpanda_api` (the dependency runs the other way: the API's bots router
depends on this package, not vice versa).
"""
from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
