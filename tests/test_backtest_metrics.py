import math

import numpy as np
import pandas as pd
import pytest

from freqpanda_backtest.equity import TradeCostResult
from freqpanda_backtest.metrics import (
    compute_drawdown,
    compute_return_ratios,
    compute_trade_stats,
    infer_periods_per_year,
)
from freqpanda_strategy import Trade


def _index(n, freq="1h"):
    return pd.date_range("2024-01-01", periods=n, freq=freq)


def test_compute_drawdown_hand_verified():
    index = _index(6)
    equity = pd.Series([100.0, 120.0, 90.0, 80.0, 110.0, 130.0], index=index)

    dd = compute_drawdown(equity)

    assert dd.max_drawdown_pct == pytest.approx((120.0 - 80.0) / 120.0)
    assert dd.peak_time == index[1]
    assert dd.trough_time == index[3]
    assert dd.recovery_time == index[5]
    assert dd.duration == index[5] - index[1]


def test_compute_drawdown_never_recovers():
    index = _index(4)
    equity = pd.Series([100.0, 120.0, 90.0, 95.0], index=index)
    dd = compute_drawdown(equity)
    assert dd.recovery_time is None
    assert dd.duration == index[-1] - index[1]


def test_compute_drawdown_monotonic_increasing_is_zero():
    index = _index(3)
    equity = pd.Series([100.0, 110.0, 120.0], index=index)
    dd = compute_drawdown(equity)
    assert dd.max_drawdown_pct == pytest.approx(0.0)


def test_compute_drawdown_empty_series():
    dd = compute_drawdown(pd.Series([], dtype=float))
    assert dd.max_drawdown_pct == 0.0
    assert dd.peak_time is None


def test_compute_return_ratios_hand_verified():
    index = _index(4)
    equity = pd.Series([100.0, 110.0, 99.0, 108.9], index=index)

    sharpe, sortino = compute_return_ratios(equity, periods_per_year=1.0, risk_free_rate=0.0)

    returns = [0.10, -0.10, 0.10]
    mean = sum(returns) / 3
    variance = sum((r - mean) ** 2 for r in returns) / (3 - 1)
    std = math.sqrt(variance)
    expected_sharpe = mean / std

    downside_sq = sum(min(r, 0.0) ** 2 for r in returns) / 3
    expected_sortino = mean / math.sqrt(downside_sq)

    assert sharpe == pytest.approx(expected_sharpe)
    assert sortino == pytest.approx(expected_sortino)


def test_compute_return_ratios_no_variance_is_nan():
    index = _index(3)
    equity = pd.Series([100.0, 100.0, 100.0], index=index)
    sharpe, sortino = compute_return_ratios(equity, periods_per_year=1.0)
    assert math.isnan(sharpe)
    assert math.isnan(sortino)


def test_compute_return_ratios_empty_series():
    sharpe, sortino = compute_return_ratios(pd.Series([], dtype=float), periods_per_year=1.0)
    assert math.isnan(sharpe)
    assert math.isnan(sortino)


def test_infer_periods_per_year_hourly():
    index = _index(100, freq="1h")
    assert infer_periods_per_year(index) == pytest.approx(365 * 24)


def test_infer_periods_per_year_daily():
    index = _index(100, freq="1D")
    assert infer_periods_per_year(index) == pytest.approx(365)


def _trade_cost_result(net_pnl_abs, net_pnl_pct):
    index = _index(2)
    trade = Trade(
        entry_time=index[0],
        entry_price=100.0,
        exit_time=index[1],
        exit_price=100.0 * (1 + net_pnl_pct),
        exit_reason="exit_signal",
        pnl_pct=net_pnl_pct,
    )
    return TradeCostResult(
        trade=trade,
        entry_fill_price=100.0,
        exit_fill_price=100.0 * (1 + net_pnl_pct),
        quantity=1.0,
        equity_before=1000.0,
        equity_after=1000.0 + net_pnl_abs,
        net_pnl_pct=net_pnl_pct,
        net_pnl_abs=net_pnl_abs,
    )


def test_compute_trade_stats_hand_verified():
    trade_costs = [
        _trade_cost_result(100.0, 0.1),
        _trade_cost_result(-50.0, -0.05),
        _trade_cost_result(200.0, 0.2),
        _trade_cost_result(-25.0, -0.025),
        _trade_cost_result(0.0, 0.0),
    ]
    stats = compute_trade_stats(trade_costs)

    assert stats.num_trades == 5
    assert stats.win_rate == pytest.approx(0.4)
    assert stats.avg_win_pct == pytest.approx(0.15)
    assert stats.avg_loss_pct == pytest.approx(-0.0375)
    assert stats.profit_factor == pytest.approx(300.0 / 75.0)


def test_compute_trade_stats_no_trades():
    stats = compute_trade_stats([])
    assert stats.num_trades == 0
    assert math.isnan(stats.win_rate)


def test_compute_trade_stats_no_losses_gives_infinite_profit_factor():
    trade_costs = [_trade_cost_result(100.0, 0.1), _trade_cost_result(50.0, 0.05)]
    stats = compute_trade_stats(trade_costs)
    assert stats.profit_factor == math.inf
