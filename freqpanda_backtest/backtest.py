"""The main entrypoint: run a strategy definition over OHLCV data and turn
the resulting trades into a full `BacktestResult`.

This function does not itself vectorize signal generation -- it calls
`freqpanda_strategy.run_strategy`, which is an intentionally sequential
per-candle interpreter (a phase-1 design requirement, so backtest and live
execution never drift apart). What *is* vectorized here is everything phase
3 owns: building the equity curve and computing every metric, all via numpy
array/pandas-vector operations rather than Python-level loops over candles
or trades. See the README's benchmark section for where the time actually
goes and why that's the right place to optimize.
"""
from __future__ import annotations

import pandas as pd

from freqpanda_strategy import StrategyDefinition, run_strategy

from .costs import TradingCosts
from .equity import apply_costs_to_trades, build_equity_curve
from .metrics import compute_drawdown, compute_return_ratios, compute_trade_stats, infer_periods_per_year
from .result import BacktestResult


def backtest(
    definition: StrategyDefinition,
    df: pd.DataFrame,
    initial_capital: float = 10_000.0,
    fee_pct: float = 0.001,
    slippage_pct: float = 0.0,
    risk_free_rate: float = 0.0,
) -> BacktestResult:
    """Run one strategy definition over `df` and return its performance.

    `fee_pct` and `slippage_pct` are fractions applied per fill (so per
    trade, both are paid twice: once on entry, once on exit) -- see
    `freqpanda_backtest.costs.TradingCosts`. `risk_free_rate` is an annual
    fraction used only for the Sharpe/Sortino excess-return baseline
    (default 0, the common choice for crypto backtests).
    """
    trades = run_strategy(definition, df)
    costs = TradingCosts(fee_pct=fee_pct, slippage_pct=slippage_pct)
    trade_costs = apply_costs_to_trades(trades, initial_capital, costs)
    equity_curve = build_equity_curve(df, trade_costs, initial_capital)

    periods_per_year = infer_periods_per_year(df.index)
    sharpe, sortino = compute_return_ratios(equity_curve, periods_per_year, risk_free_rate)
    drawdown = compute_drawdown(equity_curve)
    trade_stats = compute_trade_stats(trade_costs)

    final_capital = float(equity_curve.iloc[-1]) if len(equity_curve) else initial_capital

    return BacktestResult(
        strategy_name=definition.name,
        initial_capital=initial_capital,
        final_capital=final_capital,
        total_return_pct=(final_capital / initial_capital) - 1,
        total_return_abs=final_capital - initial_capital,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown_pct=drawdown.max_drawdown_pct,
        max_drawdown_duration=drawdown.duration,
        num_trades=trade_stats.num_trades,
        win_rate=trade_stats.win_rate,
        avg_win_pct=trade_stats.avg_win_pct,
        avg_loss_pct=trade_stats.avg_loss_pct,
        profit_factor=trade_stats.profit_factor,
        trades=trade_costs,
        equity_curve=equity_curve,
        costs=costs,
    )
