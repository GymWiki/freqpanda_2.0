"""Thin CCXT wrapper: create an exchange client and page through its OHLCV
history from a given starting point.

Rate limiting is delegated entirely to CCXT: `enableRateLimit: True` makes
every call to `fetch_ohlcv` block for whatever delay the exchange's
documented rate limit requires before it fires the request, so backfilling
years of history in a loop does not hammer the API. There is deliberately
no additional manual `time.sleep` here -- that would either be redundant
with CCXT's throttle or, worse, drift out of sync with it.
"""
from __future__ import annotations

from typing import Iterator, List, Sequence

import ccxt

# CCXT candle row: [timestamp_ms, open, high, low, close, volume]
Candle = Sequence[float]

DEFAULT_PAGE_LIMIT = 1000


def create_exchange(exchange_id: str) -> ccxt.Exchange:
    try:
        exchange_class = getattr(ccxt, exchange_id)
    except AttributeError as exc:
        raise ValueError(f"Unknown CCXT exchange id '{exchange_id}'") from exc
    return exchange_class({"enableRateLimit": True})


def fetch_ohlcv_since(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> Iterator[List[Candle]]:
    """Yield successive pages of raw CCXT OHLCV candles from `since_ms`
    onward, oldest first, until the exchange has no more data to give.

    Each `fetch_ohlcv` call already respects CCXT's rate limiter, so this
    can safely be used to pull a multi-year backfill in one call without a
    manual delay loop.
    """
    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000
    cursor = since_ms
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        if not batch:
            return
        yield batch

        next_cursor = batch[-1][0] + timeframe_ms
        if next_cursor <= cursor:
            # Exchange returned data that didn't advance the cursor -- stop
            # rather than looping forever on the same page.
            return
        cursor = next_cursor

        if len(batch) < limit:
            # Fewer candles than requested means we've caught up to the
            # most recent data the exchange has.
            return


def is_closed_candle(candle: Candle, timeframe_ms: int, now_ms: int) -> bool:
    """True if `candle` has fully closed as of `now_ms`.

    Exchanges commonly include the still-forming current candle in the last
    page of results; storing it would mean overwriting it later with
    different values every time it's re-fetched mid-candle, and briefly
    exposing wrong (incomplete) data to readers in the meantime.
    """
    return candle[0] + timeframe_ms <= now_ms
