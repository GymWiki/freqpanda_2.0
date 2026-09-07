"""Per-request Postgres connections for the API.

Reuses `freqpanda_data.db.get_connection` (phase 2) rather than
reimplementing "open a psycopg2 connection to Supabase from an env var" --
that function is already exactly this, generic to any table. jsonb values
are written with `psycopg2.extras.Json(...)` at each call site (psycopg2's
idiomatic wrapper); reads come back as plain dicts/lists automatically,
psycopg2 adapts json/jsonb columns both ways with no extra setup.
"""
from __future__ import annotations

from typing import Iterator

from freqpanda_data.db import get_connection as _get_connection

from .config import get_settings


def get_db() -> Iterator:
    """FastAPI dependency: one connection per request, always closed
    afterward. Not pooled -- see the README for why that's an acceptable
    starting point for a single small VPS, and the upgrade path
    (psycopg2.pool / pgbouncer) if it stops being one.
    """
    conn = _get_connection(get_settings().database_url)
    try:
        yield conn
    finally:
        conn.close()
