"""The strategy-agnostic interpreter: turns a `StrategyDefinition` + an OHLCV
DataFrame into a list of `Trade`s.

The interpreter only ever looks at the generic schema (indicators, condition
trees, risk parameters) and the indicator registry -- it never special-cases
a particular strategy. The same function is meant to be reused, unchanged,
for backtesting and (in a later phase) live execution, so it must not do
anything that depends on running "as fast as possible over a whole
DataFrame" versus "one new candle at a time" -- see the README for how that
guarantee is upheld.

Execution model (documented here since these are judgment calls the schema
itself doesn't make):
  - A strategy is long-only.
  - Entry and indicator-based exit signals fire on the candle's own close
    (the candle is treated as fully closed when its indicators are
    evaluated) -- there is no lookahead since only that candle's own OHLCV
    is used.
  - Stop-loss is checked against the candle's low, take-profit against the
    candle's high (i.e. "could this candle have hit the level intrabar"),
    which is the usual worst-case/best-case assumption when only OHLCV
    (no tick data) is available.
  - Priority when several exits trigger on the same candle: stop-loss >
    take-profit > trailing-stop > indicator exit signal (risk controls
    always win over a discretionary exit signal).
  - A position still open at the end of the DataFrame is left open and is
    NOT included in the returned trade list (no forced close, since that
    would fabricate an exit price that never happened).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional

import pandas as pd

from .conditions import evaluate_condition
from .exceptions import StrategyValidationError
from .indicators import INDICATOR_REGISTRY
from .schema import IndicatorConfig, StrategyDefinition, resolve_param
from .validation import validate_definition

ExitReason = Literal["stop_loss", "take_profit", "trailing_stop", "exit_signal"]

REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: ExitReason
    pnl_pct: float


def compute_indicators(df: pd.DataFrame, indicators: List[IndicatorConfig]) -> pd.DataFrame:
    """Return a copy of `df` with one extra column per indicator output."""
    result = df.copy()
    for ind in indicators:
        handler = INDICATOR_REGISTRY[ind.name]
        params = {name: resolve_param(value) for name, value in ind.params.items()}
        for column, series in handler.compute(result, ind.alias, params).items():
            result[column] = series
    return result


def run_strategy(definition: StrategyDefinition, df: pd.DataFrame) -> List[Trade]:
    """Run one strategy definition over historical OHLCV data.

    `df` must have a sorted DatetimeIndex (oldest first) and `open`, `high`,
    `low`, `close`, `volume` columns.
    """
    validate_definition(definition)

    missing = [c for c in REQUIRED_OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise StrategyValidationError(
            f"Input DataFrame is missing required OHLCV column(s): {missing}"
        )

    data = compute_indicators(df, definition.indicators)

    entry_signal = evaluate_condition(definition.entry_conditions, data)
    if definition.exit_conditions is not None:
        exit_signal = evaluate_condition(definition.exit_conditions, data)
    else:
        exit_signal = pd.Series(False, index=data.index)

    risk = definition.risk_management
    trades: List[Trade] = []

    in_position = False
    entry_price: Optional[float] = None
    entry_time: Optional[pd.Timestamp] = None
    highest_since_entry: Optional[float] = None

    for ts, row in data.iterrows():
        if not in_position:
            if bool(entry_signal.loc[ts]):
                in_position = True
                entry_price = float(row["close"])
                entry_time = ts
                highest_since_entry = entry_price
            continue

        highest_since_entry = max(highest_since_entry, float(row["high"]))

        exit_price: Optional[float] = None
        exit_reason: Optional[ExitReason] = None

        stop_loss_price = entry_price * (1 - risk.stop_loss_pct)
        if float(row["low"]) <= stop_loss_price:
            exit_price, exit_reason = stop_loss_price, "stop_loss"

        if exit_reason is None:
            take_profit_price = entry_price * (1 + risk.take_profit_pct)
            if float(row["high"]) >= take_profit_price:
                exit_price, exit_reason = take_profit_price, "take_profit"

        if exit_reason is None and risk.trailing_stop_pct is not None:
            trailing_stop_price = highest_since_entry * (1 - risk.trailing_stop_pct)
            if float(row["low"]) <= trailing_stop_price:
                exit_price, exit_reason = trailing_stop_price, "trailing_stop"

        if exit_reason is None and bool(exit_signal.loc[ts]):
            exit_price, exit_reason = float(row["close"]), "exit_signal"

        if exit_reason is not None:
            trades.append(
                Trade(
                    entry_time=entry_time,
                    entry_price=entry_price,
                    exit_time=ts,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    pnl_pct=(exit_price / entry_price) - 1,
                )
            )
            in_position = False
            entry_price = entry_time = highest_since_entry = None

    return trades
