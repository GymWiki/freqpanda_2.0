import math

import pandas as pd
import pytest

from freqpanda_backtest import backtest
from freqpanda_strategy import RiskManagement, StrategyDefinition


def _ohlcv(closes):
    n = len(closes)
    index = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1.0] * n},
        index=index,
    )


def _definition(entry, exit_, risk):
    return StrategyDefinition(
        name="trivial",
        indicators=[],
        entry_conditions=entry,
        exit_conditions=exit_,
        risk_management=RiskManagement(**risk),
    )


def test_backtest_single_trade_no_costs_matches_hand_computation():
    # Enter as soon as close > 100 (at close=105), exit as soon as close < 100 (at close=95).
    df = _ohlcv([100, 105, 105, 95])
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_={"type": "comparison", "left": "close", "op": "lt", "right": 100},
        risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )

    result = backtest(definition, df, initial_capital=10_000.0, fee_pct=0.0, slippage_pct=0.0)

    assert result.num_trades == 1
    expected_final = 10_000.0 * (95 / 105)
    assert result.final_capital == pytest.approx(expected_final)
    assert result.total_return_pct == pytest.approx((95 / 105) - 1)
    assert result.win_rate == pytest.approx(0.0)  # a loss
    assert result.profit_factor == pytest.approx(0.0)


def test_backtest_applies_fees():
    df = _ohlcv([100, 105, 105, 95])
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_={"type": "comparison", "left": "close", "op": "lt", "right": 100},
        risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )

    result = backtest(definition, df, initial_capital=10_000.0, fee_pct=0.01, slippage_pct=0.0)

    expected_final = 10_000.0 * (1 - 0.01) ** 2 * (95 / 105)
    assert result.final_capital == pytest.approx(expected_final)


def test_backtest_no_trades_is_flat_and_well_defined():
    df = _ohlcv([100, 100, 100, 100])
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 1_000_000},
        exit_=None,
        risk={"stop_loss_pct": 0.1, "take_profit_pct": 0.1},
    )

    result = backtest(definition, df, initial_capital=10_000.0)

    assert result.num_trades == 0
    assert result.final_capital == pytest.approx(10_000.0)
    assert result.total_return_pct == pytest.approx(0.0)
    assert result.max_drawdown_pct == pytest.approx(0.0)


def test_backtest_result_serialization_helpers():
    df = _ohlcv([100, 105, 105, 95])
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_={"type": "comparison", "left": "close", "op": "lt", "right": 100},
        risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    result = backtest(definition, df)

    metrics = result.metrics_dict()
    assert metrics["strategy_name"] == "trivial"
    assert isinstance(metrics["max_drawdown_duration_seconds"], float)

    trade_records = result.trade_records()
    assert len(trade_records) == 1
    assert isinstance(trade_records[0]["entry_time"], str)

    equity_records = result.equity_curve_records()
    assert len(equity_records) == len(df)
    assert isinstance(equity_records[0]["timestamp"], str)


def test_backtest_two_winning_trades_profit_factor_infinite():
    # Two independent round trips, both exiting higher than they entered:
    # entry@105 -> exit@110 (win), then entry@102 -> exit@112 (win).
    df = _ohlcv([100, 105, 110, 95, 102, 112])
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_={"type": "comparison", "left": "close", "op": "gt", "right": 108},
        risk={"stop_loss_pct": 0.9, "take_profit_pct": 0.9},
    )
    result = backtest(definition, df, fee_pct=0.0)

    assert result.num_trades == 2
    assert result.win_rate == pytest.approx(1.0)
    assert result.profit_factor == math.inf
    expected_final = 10_000.0 * (110 / 105) * (112 / 102)
    assert result.final_capital == pytest.approx(expected_final)
