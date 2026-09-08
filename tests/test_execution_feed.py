"""Tests for the polling path and the shared dedup/trim logic in
`RealtimeFeed`. The websocket path needs a live exchange connection and
isn't covered here -- see `feed.py`'s module docstring.
"""
import asyncio

import pandas as pd
import pytest

from freqpanda_execution.feed import RealtimeFeed

HOUR_MS = 3_600_000


def _seed_history(timestamps_ms):
    index = pd.DatetimeIndex([pd.Timestamp(t, unit="ms", tz="UTC") for t in timestamps_ms])
    n = len(timestamps_ms)
    return pd.DataFrame(
        {"open": [1.0] * n, "high": [1.0] * n, "low": [1.0] * n, "close": [1.0] * n, "volume": [1.0] * n},
        index=index,
    )


def _candle(ts_ms, close=2.0):
    return [ts_ms, close, close, close, close, 1.0]


class FakeExchange:
    def __init__(self, batches, timeframe_seconds=3600, now_ms=0):
        self._batches = list(batches)
        self._timeframe_seconds = timeframe_seconds
        self._now_ms = now_ms

    def parse_timeframe(self, timeframe):
        return self._timeframe_seconds

    def milliseconds(self):
        return self._now_ms

    def fetch_ohlcv(self, symbol, timeframe=None, since=None, limit=None):
        if self._batches:
            return self._batches.pop(0)
        return []


def test_feed_requires_at_least_one_seed_candle():
    with pytest.raises(ValueError):
        RealtimeFeed("binance", "BTC/USDT", "1h", pd.DataFrame())


def test_append_candle_skips_stale_or_duplicate_rows():
    feed = RealtimeFeed("binance", "BTC/USDT", "1h", _seed_history([0]))
    assert feed._append_candle(_candle(0)) is None  # exact duplicate
    assert feed._append_candle(_candle(-HOUR_MS)) is None  # older than the last row
    assert len(feed.history) == 1


def test_append_candle_appends_a_newer_row():
    feed = RealtimeFeed("binance", "BTC/USDT", "1h", _seed_history([0]))
    history = feed._append_candle(_candle(HOUR_MS, close=42.0))
    assert history is not None
    assert len(feed.history) == 2
    assert feed.history["close"].iloc[-1] == 42.0


def test_append_candle_trims_to_max_history():
    feed = RealtimeFeed("binance", "BTC/USDT", "1h", _seed_history([0, HOUR_MS, 2 * HOUR_MS]), max_history=3)
    feed._append_candle(_candle(3 * HOUR_MS, close=99.0))
    assert len(feed.history) == 3
    assert list(feed.history.index) == [
        pd.Timestamp(HOUR_MS, unit="ms", tz="UTC"),
        pd.Timestamp(2 * HOUR_MS, unit="ms", tz="UTC"),
        pd.Timestamp(3 * HOUR_MS, unit="ms", tz="UTC"),
    ]


def test_run_polling_invokes_callback_once_per_newly_closed_candle():
    exchange = FakeExchange(
        batches=[[_candle(HOUR_MS, close=10.0), _candle(2 * HOUR_MS, close=11.0)]],
        timeframe_seconds=3600,
        now_ms=3 * HOUR_MS,
    )
    feed = RealtimeFeed("binance", "BTC/USDT", "1h", _seed_history([0]), poll_interval_seconds=0.01)
    stop_event = asyncio.Event()
    seen_closes = []

    def on_candle_close(history: pd.DataFrame) -> None:
        seen_closes.append(history["close"].iloc[-1])
        if len(seen_closes) == 2:
            stop_event.set()

    asyncio.run(asyncio.wait_for(feed._run_polling(exchange, on_candle_close, stop_event), timeout=5))

    assert seen_closes == [10.0, 11.0]
    assert len(feed.history) == 3


def test_run_polling_skips_candles_not_yet_closed():
    exchange = FakeExchange(
        batches=[[_candle(HOUR_MS, close=10.0)]],
        timeframe_seconds=3600,
        now_ms=HOUR_MS,  # candle isn't closed until now_ms >= HOUR_MS + HOUR_MS
    )
    feed = RealtimeFeed("binance", "BTC/USDT", "1h", _seed_history([0]), poll_interval_seconds=0.01)
    stop_event = asyncio.Event()

    async def _stop_soon():
        await asyncio.sleep(0.03)
        stop_event.set()

    async def _run():
        await asyncio.gather(feed._run_polling(exchange, lambda h: None, stop_event), _stop_soon())

    asyncio.run(asyncio.wait_for(_run(), timeout=5))
    assert len(feed.history) == 1  # never appended -- the candle was never "closed"


async def _await_callback(callback, history):
    result = callback(history)
    if asyncio.iscoroutine(result):
        await result


def test_run_polling_supports_an_async_callback():
    exchange = FakeExchange(
        batches=[[_candle(HOUR_MS, close=10.0)]],
        timeframe_seconds=3600,
        now_ms=2 * HOUR_MS,
    )
    feed = RealtimeFeed("binance", "BTC/USDT", "1h", _seed_history([0]), poll_interval_seconds=0.01)
    stop_event = asyncio.Event()
    seen = []

    async def on_candle_close(history: pd.DataFrame) -> None:
        seen.append(history["close"].iloc[-1])
        stop_event.set()

    asyncio.run(asyncio.wait_for(feed._run_polling(exchange, on_candle_close, stop_event), timeout=5))
    assert seen == [10.0]
