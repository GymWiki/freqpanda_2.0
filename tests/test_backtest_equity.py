import numpy as np
import pandas as pd
import pytest

from freqpanda_backtest.costs import TradingCosts
from freqpanda_backtest.equity import apply_costs_to_trades, build_equity_curve
from freqpanda_strategy import Trade


def _trade(entry_time, entry_price, exit_time, exit_price, reason="exit_signal"):
    return Trade(
        entry_time=entry_time,
        entry_price=entry_price,
        exit_time=exit_time,
        exit_price=exit_price,
        exit_reason=reason,
        pnl_pct=(exit_price / entry_price) - 1,
    )


def _index(n, freq="1h"):
    return pd.date_range("2024-01-01", periods=n, freq=freq)


def test_apply_costs_no_fees_matches_raw_pnl():
    index = _index(3)
    trades = [
        _trade(index[0], 100.0, index[1], 110.0),
        _trade(index[1], 110.0, index[2], 99.0),
    ]
    results = apply_costs_to_trades(trades, initial_capital=10_000.0, costs=TradingCosts())

    assert results[0].equity_before == 10_000.0
    assert results[0].equity_after == pytest.approx(11_000.0)
    assert results[0].net_pnl_pct == pytest.approx(0.10)

    assert results[1].equity_before == pytest.approx(11_000.0)
    assert results[1].equity_after == pytest.approx(9_900.0)
    assert results[1].net_pnl_pct == pytest.approx(-0.10)


def test_apply_costs_with_fee_matches_hand_computed_value():
    # By hand: entry 100 -> exit 110, 1% fee on both fills.
    # quantity = 10000 * 0.99 / 100 = 99
    # proceeds = 99 * 110 = 10890
    # equity_after = 10890 * 0.99 = 10781.1
    # net_pnl_pct = (1-0.01)**2 * (110/100) - 1 = 0.07811
    index = _index(2)
    trades = [_trade(index[0], 100.0, index[1], 110.0)]
    costs = TradingCosts(fee_pct=0.01)

    results = apply_costs_to_trades(trades, initial_capital=10_000.0, costs=costs)

    assert results[0].equity_after == pytest.approx(10_781.1)
    assert results[0].net_pnl_pct == pytest.approx(0.07811, abs=1e-9)


def test_apply_costs_empty_trade_list():
    assert apply_costs_to_trades([], 10_000.0, TradingCosts()) == []


def test_build_equity_curve_marks_to_market_between_entry_and_exit():
    index = _index(5)
    df = pd.DataFrame(
        {
            "open": [100, 105, 110, 108, 120],
            "high": [100, 105, 110, 108, 120],
            "low": [100, 105, 110, 108, 120],
            "close": [100.0, 105.0, 110.0, 108.0, 120.0],
            "volume": [1.0] * 5,
        },
        index=index,
    )
    trades = [
        _trade(index[0], 100.0, index[2], 110.0),
        _trade(index[3], 108.0, index[4], 120.0),
    ]
    trade_costs = apply_costs_to_trades(trades, initial_capital=10_000.0, costs=TradingCosts())

    equity = build_equity_curve(df, trade_costs, initial_capital=10_000.0)

    # trade 1: enter at close[0]=100 -> quantity=100; mark at close[1]=105 -> 10500; exit at close[2]=110 -> 11000
    # trade 2: enter at close[3]=108 -> quantity=11000/108; exit at close[4]=120 -> 11000/108*120
    expected = [10_000.0, 10_500.0, 11_000.0, 11_000.0, 11_000.0 / 108.0 * 120.0]
    assert equity.tolist() == pytest.approx(expected)
    assert list(equity.index) == list(index)


def test_build_equity_curve_flat_when_no_trades():
    index = _index(4)
    df = pd.DataFrame(
        {"open": [1] * 4, "high": [1] * 4, "low": [1] * 4, "close": [1.0] * 4, "volume": [1.0] * 4},
        index=index,
    )
    equity = build_equity_curve(df, [], initial_capital=5_000.0)
    assert equity.tolist() == [5_000.0] * 4


def test_build_equity_curve_flat_gap_before_first_trade():
    index = _index(4)
    df = pd.DataFrame(
        {
            "open": [1, 1, 1, 1],
            "high": [1, 1, 1, 1],
            "low": [1, 1, 1, 1],
            "close": [100.0, 100.0, 100.0, 105.0],
            "volume": [1.0] * 4,
        },
        index=index,
    )
    trades = [_trade(index[2], 100.0, index[3], 105.0)]
    trade_costs = apply_costs_to_trades(trades, initial_capital=1_000.0, costs=TradingCosts())
    equity = build_equity_curve(df, trade_costs, initial_capital=1_000.0)
    assert equity.tolist() == pytest.approx([1_000.0, 1_000.0, 1_000.0, 1_050.0])
