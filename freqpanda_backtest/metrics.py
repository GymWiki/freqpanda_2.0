"""Performance metrics computed from an equity curve and a list of
cost-adjusted trades. Every computation here is vectorized numpy/pandas
math over the (small) trade list or the equity curve array -- there is no
per-candle or per-trade Python-level aggregation loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .equity import TradeCostResult


@dataclass(frozen=True)
class DrawdownInfo:
    max_drawdown_pct: float  # positive fraction, e.g. 0.23 == 23% drawdown
    peak_time: Optional[pd.Timestamp]
    trough_time: Optional[pd.Timestamp]
    recovery_time: Optional[pd.Timestamp]  # None if never recovered by the end of the data
    duration: pd.Timedelta  # peak -> recovery, or peak -> end of data if unrecovered


@dataclass(frozen=True)
class TradeStats:
    num_trades: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float


def infer_periods_per_year(index: pd.DatetimeIndex) -> float:
    """Estimate how many candles a year holds, from the median spacing
    between consecutive timestamps -- avoids requiring the caller to pass
    the timeframe string separately (the DataFrame from phase 2 doesn't
    carry it as metadata) while staying robust to the occasional gap.
    """
    if len(index) < 2:
        return float("nan")
    median_delta = index.to_series().diff().median()
    return pd.Timedelta(days=365) / median_delta


def compute_drawdown(equity: pd.Series) -> DrawdownInfo:
    if equity.empty:
        return DrawdownInfo(0.0, None, None, None, pd.Timedelta(0))

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    trough_time = drawdown.idxmin()
    max_dd = float(-drawdown.loc[trough_time])

    peak_time = equity.loc[:trough_time].idxmax()
    peak_value = equity.loc[peak_time]

    after_trough = equity.loc[trough_time:]
    recovered = after_trough[after_trough >= peak_value]
    if len(recovered) > 0:
        recovery_time = recovered.index[0]
        duration = recovery_time - peak_time
    else:
        recovery_time = None
        duration = equity.index[-1] - peak_time

    return DrawdownInfo(max_dd, peak_time, trough_time, recovery_time, duration)


def compute_return_ratios(
    equity: pd.Series, periods_per_year: float, risk_free_rate: float = 0.0
) -> Tuple[float, float]:
    """Annualized Sharpe and Sortino ratios from per-candle equity returns.

    Using per-candle returns (rather than per-trade returns) makes these
    genuinely time-weighted: candles spent flat between trades correctly
    contribute a zero return and reduce volatility, instead of being
    invisible to the calculation.

    Sortino's downside deviation follows the standard definition: the RMS of
    `min(return - MAR, 0)` over *all* periods (not just the losing ones),
    with MAR (minimum acceptable return) the per-period risk-free rate.
    """
    returns = equity.pct_change().dropna()
    if returns.empty:
        return float("nan"), float("nan")

    mar = risk_free_rate / periods_per_year if periods_per_year and not np.isnan(periods_per_year) else 0.0
    excess = returns - mar
    mean_excess = float(excess.mean())

    std = float(returns.std(ddof=1))
    if std > 0:
        sharpe = mean_excess / std * np.sqrt(periods_per_year)
    else:
        sharpe = float("nan")

    downside = np.minimum(returns.to_numpy() - mar, 0.0)
    downside_deviation = float(np.sqrt(np.mean(downside**2)))
    if downside_deviation > 0:
        sortino = mean_excess / downside_deviation * np.sqrt(periods_per_year)
    else:
        sortino = float("inf") if mean_excess > 0 else float("nan")

    return float(sharpe), float(sortino)


def compute_trade_stats(trade_costs: Sequence[TradeCostResult]) -> TradeStats:
    n = len(trade_costs)
    if n == 0:
        return TradeStats(0, float("nan"), float("nan"), float("nan"), float("nan"))

    pnl_abs = np.array([tc.net_pnl_abs for tc in trade_costs])
    pnl_pct = np.array([tc.net_pnl_pct for tc in trade_costs])
    wins = pnl_abs > 0
    losses = pnl_abs < 0

    win_rate = float(np.count_nonzero(wins) / n)
    avg_win_pct = float(pnl_pct[wins].mean()) if wins.any() else 0.0
    avg_loss_pct = float(pnl_pct[losses].mean()) if losses.any() else 0.0

    gross_profit = float(pnl_abs[wins].sum()) if wins.any() else 0.0
    gross_loss = float(-pnl_abs[losses].sum()) if losses.any() else 0.0
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = float("nan")

    return TradeStats(n, win_rate, avg_win_pct, avg_loss_pct, profit_factor)
