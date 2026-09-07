"""The structured output of one backtest run: summary metrics + the
cost-adjusted trade list + the equity curve, plus small serialization
helpers so phase 5 (Supabase) and phase 6 (dashboard) don't need to know
about this module's internal dataclasses to consume the result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from .costs import TradingCosts
from .equity import TradeCostResult


@dataclass(frozen=True)
class BacktestResult:
    strategy_name: str
    initial_capital: float
    final_capital: float
    total_return_pct: float
    total_return_abs: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration: pd.Timedelta
    num_trades: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    trades: List[TradeCostResult]
    equity_curve: pd.Series
    costs: TradingCosts

    def metrics_dict(self) -> dict:
        """Scalar metrics only -- one flat dict, i.e. one row for a Supabase
        `backtest_runs` table. Timestamps/timedeltas are converted to
        JSON-friendly types.
        """
        return {
            "strategy_name": self.strategy_name,
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_return_pct": self.total_return_pct,
            "total_return_abs": self.total_return_abs,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_duration_seconds": self.max_drawdown_duration.total_seconds(),
            "num_trades": self.num_trades,
            "win_rate": self.win_rate,
            "avg_win_pct": self.avg_win_pct,
            "avg_loss_pct": self.avg_loss_pct,
            "profit_factor": self.profit_factor,
            "fee_pct": self.costs.fee_pct,
            "slippage_pct": self.costs.slippage_pct,
        }

    def trade_records(self) -> List[dict]:
        """One dict per trade -- rows for a Supabase `backtest_trades` table."""
        return [
            {
                "entry_time": tc.trade.entry_time.isoformat(),
                "exit_time": tc.trade.exit_time.isoformat(),
                "entry_price": tc.trade.entry_price,
                "exit_price": tc.trade.exit_price,
                "entry_fill_price": tc.entry_fill_price,
                "exit_fill_price": tc.exit_fill_price,
                "exit_reason": tc.trade.exit_reason,
                "quantity": tc.quantity,
                "net_pnl_pct": tc.net_pnl_pct,
                "net_pnl_abs": tc.net_pnl_abs,
            }
            for tc in self.trades
        ]

    def equity_curve_records(self) -> List[dict]:
        """One dict per candle -- rows for a Supabase `backtest_equity` table
        (or directly what a dashboard chart wants).
        """
        return [
            {"timestamp": ts.isoformat(), "equity": float(value)}
            for ts, value in self.equity_curve.items()
        ]
