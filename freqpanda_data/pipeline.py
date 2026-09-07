"""Orchestrates fetch + store for one or more symbol/timeframe pairs.

`update_symbol_timeframe` is the incremental-update core: it looks up the
latest candle already stored, resumes fetching from right after it (or from
`config.backfill_since` when nothing is stored yet), drops any still-forming
candle, and upserts the rest. `run_pipeline` just loops that over every pair
in a `PipelineConfig`.

How you invoke `run_pipeline` is deliberately left open for this phase --
run it from a script, a cron job, or (phase 5) a job queue; nothing here
assumes a particular scheduler.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from .config import PipelineConfig
from .db import get_connection, get_latest_timestamp_ms, upsert_candles
from .exchange import create_exchange, fetch_ohlcv_since, is_closed_candle

logger = logging.getLogger(__name__)


def update_symbol_timeframe(
    conn,
    exchange,
    exchange_id: str,
    symbol: str,
    timeframe: str,
    default_since_ms: int,
) -> int:
    """Fetch and store any candles newer than what's already in the
    database for this (symbol, timeframe). Returns the number of candles
    written.
    """
    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000
    latest_ms = get_latest_timestamp_ms(conn, exchange_id, symbol, timeframe)
    since_ms = latest_ms + timeframe_ms if latest_ms is not None else default_since_ms

    now_ms = exchange.milliseconds()
    if since_ms >= now_ms:
        return 0

    total_written = 0
    for batch in fetch_ohlcv_since(exchange, symbol, timeframe, since_ms):
        closed = [c for c in batch if is_closed_candle(c, timeframe_ms, exchange.milliseconds())]
        total_written += upsert_candles(conn, exchange_id, symbol, timeframe, closed)
    return total_written


def run_pipeline(config: PipelineConfig) -> Dict[str, Optional[int]]:
    """Update every symbol/timeframe pair in `config`. Returns a dict of
    "SYMBOL:timeframe" -> number of candles written (None if that pair
    failed -- one pair's failure doesn't stop the others).
    """
    exchange = create_exchange(config.exchange_id)
    default_since_ms = exchange.parse8601(config.backfill_since)

    results: Dict[str, Optional[int]] = {}
    conn = get_connection(config.database_url)
    try:
        for pair in config.pairs:
            key = f"{pair.symbol}:{pair.timeframe}"
            try:
                written = update_symbol_timeframe(
                    conn, exchange, config.exchange_id, pair.symbol, pair.timeframe, default_since_ms
                )
                results[key] = written
                logger.info("%s: wrote %d new candle(s)", key, written)
            except Exception:
                logger.exception("%s: update failed", key)
                results[key] = None
    finally:
        conn.close()
    return results
