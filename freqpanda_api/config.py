"""Settings, all read from environment variables so the same image runs in
docker-compose, on the VPS, and in tests with nothing but env-var changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # Reuses the same env var names as freqpanda_data (phase 2) and
    # freqpanda_api both talk to the one Supabase Postgres database.
    database_url: Optional[str] = field(default_factory=lambda: os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL"))
    redis_url: str = field(default_factory=lambda: os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    api_keys: List[str] = field(default_factory=lambda: _split_csv(os.environ.get("API_KEYS")))
    default_exchange_id: str = field(default_factory=lambda: os.environ.get("DEFAULT_EXCHANGE_ID", "binance"))
    job_queue_name: str = field(default_factory=lambda: os.environ.get("JOB_QUEUE_NAME", "freqpanda"))
    job_timeout_seconds: int = field(default_factory=lambda: int(os.environ.get("JOB_TIMEOUT_SECONDS", "1800")))


def get_settings() -> Settings:
    return Settings()
