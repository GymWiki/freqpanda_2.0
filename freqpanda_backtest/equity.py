"""Turns the phase-1 interpreter's trade list into (a) net-of-cost per-trade
results and (b) a continuous, mark-to-market equity curve over every candle.

Position sizing assumption (a judgment call the schema doesn't make): the
strategy is long-only and the interpreter holds at most one open position at
a time (trades never overlap), so every trade deploys the *entire* current
equity and fully realizes it back to cash at exit before the next trade can
open -- there is no separate position-sizing/leverage model in phase 1 to
plug in here. This compounds gains and losses across trades, which is the
standard default absent an explicit sizing rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np
import pandas as pd

from freqpanda_strategy import Trade

from .costs import TradingCosts


@dataclass(frozen=True)
class TradeCostResult:
    """One trade, plus the effect of fees/slippage and the equity impact."""

    trade: Trade
    entry_fill_price: float
    exit_fill_price: float
    quantity: float
    equity_before: float
    equity_after: float
    net_pnl_pct: float
    net_pnl_abs: float


def apply_costs_to_trades(
    trades: Sequence[Trade], initial_capital: float, costs: TradingCosts
) -> List[TradeCostResult]:
    """Walk trades in chronological order, compounding equity through each.

    For trade i with equity E_i going in:
      - buy at `entry_fill_price` (raw price adjusted for slippage), paying
        `fee_pct` on the notional: quantity = E_i * (1 - fee_pct) / entry_fill_price
      - sell at `exit_fill_price` (raw price adjusted for slippage), paying
        `fee_pct` again on the proceeds: E_{i+1} = quantity * exit_fill_price * (1 - fee_pct)

    This is a per-trade Python loop, but trade counts are small (tens to
    low thousands even for years of intraday data) compared to candle
    counts, so it costs nothing next to `run_strategy`'s per-candle loop --
    see the README's benchmark section.
    """
    equity = initial_capital
    results: List[TradeCostResult] = []
    for trade in trades:
        entry_fill = costs.entry_fill_price(trade.entry_price)
        exit_fill = costs.exit_fill_price(trade.exit_price)
        equity_before = equity

        quantity = (equity_before * (1 - costs.fee_pct)) / entry_fill
        proceeds = quantity * exit_fill
        equity_after = proceeds * (1 - costs.fee_pct)

        results.append(
            TradeCostResult(
                trade=trade,
                entry_fill_price=entry_fill,
                exit_fill_price=exit_fill,
                quantity=quantity,
                equity_before=equity_before,
                equity_after=equity_after,
                net_pnl_pct=(equity_after / equity_before) - 1,
                net_pnl_abs=equity_after - equity_before,
            )
        )
        equity = equity_after
    return results


def build_equity_curve(
    df: pd.DataFrame, trade_costs: Sequence[TradeCostResult], initial_capital: float
) -> pd.Series:
    """One equity value per candle in `df`'s index:

      - flat (idle cash) while no position is open
      - `quantity * close` mark-to-market on candles strictly between a
        trade's entry and exit (the position is open but not yet closed)
      - the entry candle is set to `equity_before * (1 - fee_pct)`, i.e. the
        paper value right after paying the entry fee, before any price move
      - the exit candle is set to the trade's actual realized `equity_after`
        (which may differ from `quantity * close` if the exit filled at a
        stop-loss/take-profit/trailing-stop level rather than the close)

    Implemented as index positions written into a numpy array (not a
    per-candle Python loop) so building the curve costs O(n_candles +
    n_trades) with a small constant, not O(n_candles * n_trades).
    """
    index = df.index
    close = df["close"].to_numpy(dtype=float)
    values = np.empty(len(index), dtype=float)

    equity_at_segment_start = initial_capital
    cursor = 0
    for tc in trade_costs:
        entry_pos = index.get_loc(tc.trade.entry_time)
        exit_pos = index.get_loc(tc.trade.exit_time)

        values[cursor:entry_pos] = equity_at_segment_start
        values[entry_pos] = tc.quantity * tc.entry_fill_price
        if exit_pos > entry_pos + 1:
            values[entry_pos + 1 : exit_pos] = tc.quantity * close[entry_pos + 1 : exit_pos]
        values[exit_pos] = tc.equity_after

        equity_at_segment_start = tc.equity_after
        cursor = exit_pos + 1

    values[cursor:] = equity_at_segment_start
    return pd.Series(values, index=index, name="equity")
