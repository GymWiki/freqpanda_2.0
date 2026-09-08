"""Settings, read from environment variables -- same pattern as
`freqpanda_api.config` and `freqpanda_data`, so the same `.env` on the VPS
configures every phase.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Settings:
    database_url: Optional[str] = field(
        default_factory=lambda: os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    )
    execution_master_key: Optional[str] = field(default_factory=lambda: os.environ.get("EXECUTION_MASTER_KEY"))
    # How often (seconds) the supervisor checks `bots.desired_status` against
    # reality and starts/stops child processes accordingly.
    supervisor_poll_interval_seconds: float = field(
        default_factory=lambda: float(os.environ.get("SUPERVISOR_POLL_INTERVAL_SECONDS", "5"))
    )
    # How often (seconds) a bot writes bot_state.last_heartbeat_at, even
    # when nothing happened -- lets the supervisor/webapp tell "quietly
    # idle between candles" apart from "process died".
    heartbeat_interval_seconds: float = field(
        default_factory=lambda: float(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "15"))
    )
    # Polling fallback interval for exchanges/timeframes without websocket
    # OHLCV support -- see freqpanda_execution/feed.py.
    poll_interval_seconds: float = field(default_factory=lambda: float(os.environ.get("FEED_POLL_INTERVAL_SECONDS", "5")))
    # Consecutive crashes within crash_loop_window_seconds before the
    # supervisor gives up on a bot and marks it 'error' instead of
    # restarting it again -- protects against hammering an exchange with a
    # bot that crashes immediately on every restart.
    max_restarts_in_window: int = field(default_factory=lambda: int(os.environ.get("MAX_RESTARTS_IN_WINDOW", "3")))
    crash_loop_window_seconds: float = field(
        default_factory=lambda: float(os.environ.get("CRASH_LOOP_WINDOW_SECONDS", "300"))
    )


def get_settings() -> Settings:
    return Settings()
