"""The live counterpart to `freqpanda_strategy.interpreter.run_strategy`.

`run_strategy` cannot be called as-is for live execution: it is designed to
walk a *complete* historical DataFrame and return only *completed* trades
(by design -- see its own docstring: an open position at the end of the
data is deliberately never exposed). Live execution needs the opposite of
that: it needs to know about an open position the moment it opens, so it
can place a real order right now, not retroactively once a matching exit
also happens to appear in a later call's output.

To keep "no new strategy logic" real rather than nominal, this module
reuses `freqpanda_strategy`'s actual strategy-interpretation primitives
unchanged:

  - `compute_indicators` -- exactly what indicator values mean
  - `evaluate_condition` -- exactly what the entry/exit condition tree means

Only the position bookkeeping loop (which candle -> which state
transition) is reimplemented here, because it fundamentally has to be: a
backtest fabricates an instant, perfect fill; live execution has to
actually place an order (`freqpanda_execution.broker`) and live with
whatever fill it gets. That loop is written to mirror
`run_strategy`'s -- same priority order (stop_loss > take_profit >
trailing_stop > exit_signal), same "check entry only while flat" rule --
and `tests/test_live_interpreter.py` pins that down with a parity test:
fed the same OHLCV data one candle at a time, this module must produce the
exact same trade list as one `run_strategy()` call over the whole
DataFrame. That test is the actual guarantee of "no drift between backtest
and live", not just a comment saying so.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from freqpanda_strategy import StrategyDefinition
from freqpanda_strategy.interpreter import compute_indicators
from freqpanda_strategy.conditions import evaluate_condition
from freqpanda_strategy.schema import RiskManagement

ExitReason = str  # "stop_loss" | "take_profit" | "trailing_stop" | "exit_signal"


@dataclass(frozen=True)
class SignalSnapshot:
    """What the entry/exit conditions evaluate to on the most recent
    (assumed fully closed) candle of `df`.
    """

    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    entry_signal: bool
    exit_signal: bool


def latest_signal(definition: StrategyDefinition, df: pd.DataFrame) -> SignalSnapshot:
    """`df` must already have the same OHLCV shape `run_strategy` expects
    (sorted ascending DatetimeIndex, open/high/low/close/volume columns),
    with its last row being the candle that just closed. Recomputes
    indicators over the whole of `df` every call -- cheap relative to a
    candle's real-world duration (phase 3's benchmark: ~240ms for 8760
    hourly candles), and the only way to guarantee the exact same
    indicator values `run_strategy` would compute over the same history.
    """
    data = compute_indicators(df, definition.indicators)

    entry_series = evaluate_condition(definition.entry_conditions, data)
    if definition.exit_conditions is not None:
        exit_series = evaluate_condition(definition.exit_conditions, data)
    else:
        exit_series = pd.Series(False, index=data.index)

    latest_ts = data.index[-1]
    row = data.loc[latest_ts]
    return SignalSnapshot(
        timestamp=latest_ts,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        entry_signal=bool(entry_series.loc[latest_ts]),
        exit_signal=bool(exit_series.loc[latest_ts]),
    )


@dataclass
class OpenPosition:
    entry_time: pd.Timestamp
    entry_price: float
    highest_since_entry: float


@dataclass(frozen=True)
class TradeAction:
    kind: str  # "enter" | "exit"
    price: float
    reason: Optional[ExitReason] = None


@dataclass
class LivePositionTracker:
    """Long-only, one position at a time -- identical constraints to
    `run_strategy`. Call `process()` once per closed candle with that
    candle's `SignalSnapshot`; it returns a `TradeAction` exactly when
    `run_strategy` would have recorded an entry or an exit on that same
    candle, in the same order of priority.
    """

    risk_management: RiskManagement
    position: Optional[OpenPosition] = field(default=None)

    def process(self, snapshot: SignalSnapshot) -> Optional[TradeAction]:
        if self.position is None:
            if snapshot.entry_signal:
                self.position = OpenPosition(
                    entry_time=snapshot.timestamp,
                    entry_price=snapshot.close,
                    highest_since_entry=snapshot.close,
                )
                return TradeAction(kind="enter", price=snapshot.close)
            return None

        self.position.highest_since_entry = max(self.position.highest_since_entry, snapshot.high)

        stop_loss_price = self.position.entry_price * (1 - self.risk_management.stop_loss_pct)
        if snapshot.low <= stop_loss_price:
            return self._close(stop_loss_price, "stop_loss")

        take_profit_price = self.position.entry_price * (1 + self.risk_management.take_profit_pct)
        if snapshot.high >= take_profit_price:
            return self._close(take_profit_price, "take_profit")

        if self.risk_management.trailing_stop_pct is not None:
            trailing_stop_price = self.position.highest_since_entry * (1 - self.risk_management.trailing_stop_pct)
            if snapshot.low <= trailing_stop_price:
                return self._close(trailing_stop_price, "trailing_stop")

        if snapshot.exit_signal:
            return self._close(snapshot.close, "exit_signal")

        return None

    def _close(self, price: float, reason: ExitReason) -> TradeAction:
        self.position = None
        return TradeAction(kind="exit", price=price, reason=reason)
