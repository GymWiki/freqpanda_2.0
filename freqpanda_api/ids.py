"""Prefixed, application-generated ids (e.g. `strat_...`, `job_...`) --
plain Python `uuid4` hex strings, not Postgres-generated uuids, so no
extension (pgcrypto/uuid-ossp) needs to be enabled on the target Supabase
project.
"""
from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
