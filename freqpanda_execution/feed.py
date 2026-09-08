"""Realtime OHLCV feed: maintains a rolling candle history for one
(exchange, symbol, timeframe) and calls back exactly once per newly closed
candle, with the updated history -- which is handed straight to
`freqpanda_execution.live_interpreter.latest_signal`, i.e. straight into
phase 1's own `compute_indicators`/`evaluate_condition`.

Uses `ccxt.pro`'s `watch_ohlcv` (websocket) when the exchange supports it;
falls back to polling `fetch_ohlcv` otherwise. Either way, "closed candle"
is decided by the exact same rule phase 2's backfill uses
(`freqpanda_data.exchange.is_closed_candle`), and the polling path reuses
phase 2's own `fetch_ohlcv_since` pagination helper -- there is no second
implementation of "how do I know a candle is really closed" or "how do I
page through CCXT's OHLCV history" in this codebase.

The websocket path needs a live exchange connection to exercise for real
and isn't unit-testable in this environment; `tests/test_feed.py` covers
the polling path (against a fake exchange, no network) and the
dedup/trim logic in `_append_candle`, which both paths share.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional, Union

import ccxt
import pandas as pd

from freqpanda_data.exchange import Candle, fetch_ohlcv_since, is_closed_candle

logger = logging.getLogger(__name__)

OnCandleClose = Union[Callable[[pd.DataFrame], None], Callable[[pd.DataFrame], Awaitable[None]]]


async def _invoke(callback: OnCandleClose, history: pd.DataFrame) -> None:
    result = callback(history)
    if asyncio.iscoroutine(result):
        await result


class RealtimeFeed:
    def __init__(
        self,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        history: pd.DataFrame,
        max_history: int = 500,
        poll_interval_seconds: float = 5.0,
    ):
        if history.empty:
            raise ValueError(
                "RealtimeFeed needs at least one seed candle to start from -- "
                "backfill this symbol/timeframe with phase 2 first."
            )
        self.exchange_id = exchange_id
        self.symbol = symbol
        self.timeframe = timeframe
        self.max_history = max_history
        self.poll_interval_seconds = poll_interval_seconds
        self.history = history.iloc[-max_history:].copy()

    def _append_candle(self, candle: Candle) -> Optional[pd.DataFrame]:
        """Appends `candle` (a raw CCXT row) if it's newer than the last
        candle already in history; returns the updated history, or `None`
        if `candle` was a duplicate/stale (already-seen) row.
        """
        ts = pd.Timestamp(candle[0], unit="ms", tz="UTC")
        if len(self.history) and ts <= self.history.index[-1]:
            return None
        row = pd.DataFrame(
            {"open": [candle[1]], "high": [candle[2]], "low": [candle[3]], "close": [candle[4]], "volume": [candle[5]]},
            index=pd.DatetimeIndex([ts]),
        )
        self.history = pd.concat([self.history, row]).iloc[-self.max_history :]
        return self.history

    async def run(self, exchange: ccxt.Exchange, on_candle_close: OnCandleClose, stop_event: asyncio.Event) -> None:
        """`exchange` is a sync `ccxt.Exchange` (e.g. from
        `freqpanda_data.exchange.create_exchange`), used for the polling
        fallback and for timeframe/clock helpers either way. A `ccxt.pro`
        async exchange is constructed internally when websocket support is
        available for `exchange_id`.
        """
        pro_exchange = self._make_pro_exchange()
        if pro_exchange is not None and pro_exchange.has.get("watchOHLCV"):
            logger.info("%s/%s: using websocket feed (ccxt.pro)", self.symbol, self.timeframe)
            try:
                await self._run_websocket(pro_exchange, on_candle_close, stop_event)
            finally:
                await pro_exchange.close()
        else:
            logger.info("%s/%s: no websocket OHLCV support on %s, polling instead", self.symbol, self.timeframe, self.exchange_id)
            await self._run_polling(exchange, on_candle_close, stop_event)

    def _make_pro_exchange(self):
        try:
            import ccxt.pro as ccxtpro
        except ImportError:
            return None
        exchange_class = getattr(ccxtpro, self.exchange_id, None)
        if exchange_class is None:
            return None
        return exchange_class({"enableRateLimit": True})

    async def _run_websocket(self, pro_exchange, on_candle_close: OnCandleClose, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            watch_task = asyncio.ensure_future(pro_exchange.watch_ohlcv(self.symbol, self.timeframe))
            stop_task = asyncio.ensure_future(stop_event.wait())
            done, pending = await asyncio.wait({watch_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            if stop_task in done:
                break

            candles = watch_task.result()
            now_ms = pro_exchange.milliseconds()
            timeframe_ms = pro_exchange.parse_timeframe(self.timeframe) * 1000
            for candle in candles:
                if not is_closed_candle(candle, timeframe_ms, now_ms):
                    continue
                history = self._append_candle(candle)
                if history is not None:
                    await _invoke(on_candle_close, history)

    async def _run_polling(self, exchange: ccxt.Exchange, on_candle_close: OnCandleClose, stop_event: asyncio.Event) -> None:
        timeframe_ms = exchange.parse_timeframe(self.timeframe) * 1000
        while not stop_event.is_set():
            since_ms = int(self.history.index[-1].timestamp() * 1000) + timeframe_ms
            now_ms = exchange.milliseconds()
            if since_ms < now_ms:
                for batch in fetch_ohlcv_since(exchange, self.symbol, self.timeframe, since_ms):
                    for candle in batch:
                        if not is_closed_candle(candle, timeframe_ms, exchange.milliseconds()):
                            continue
                        history = self._append_candle(candle)
                        if history is not None:
                            await _invoke(on_candle_close, history)

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_interval_seconds)
            except asyncio.TimeoutError:
                pass
