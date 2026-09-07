import pandas as pd
import pytest

from freqpanda_backtest.walkforward import generate_walk_forward_windows, run_walk_forward
from freqpanda_strategy import RiskManagement, StrategyDefinition

from conftest import generate_synthetic_ohlcv


def _index(n, freq="1h"):
    return pd.date_range("2024-01-01", periods=n, freq=freq)


def test_generate_windows_rolling():
    index = _index(20)  # t0..t19
    windows = generate_walk_forward_windows(
        index, train_period=pd.Timedelta(hours=8), test_period=pd.Timedelta(hours=4)
    )

    assert len(windows) == 2

    assert windows[0].train_start == index[0]
    assert windows[0].train_end == index[0] + pd.Timedelta(hours=8)
    assert windows[0].test_start == windows[0].train_end
    assert windows[0].test_end == windows[0].test_start + pd.Timedelta(hours=4)

    # rolling: the second window's train start slides forward by `step` (== test_period here)
    assert windows[1].train_start == windows[0].train_start + pd.Timedelta(hours=4)
    assert windows[1].train_end == windows[1].train_start + pd.Timedelta(hours=8)
    assert windows[1].test_start == windows[1].train_end


def test_generate_windows_anchored_train_start_stays_fixed():
    index = _index(20)
    windows = generate_walk_forward_windows(
        index,
        train_period=pd.Timedelta(hours=8),
        test_period=pd.Timedelta(hours=4),
        anchored=True,
    )

    assert len(windows) == 2
    assert windows[0].train_start == index[0]
    assert windows[1].train_start == index[0]  # anchored: never slides
    assert windows[1].train_end == windows[0].train_end + pd.Timedelta(hours=4)  # expands instead


def test_generate_windows_none_when_data_too_short():
    index = _index(5)
    windows = generate_walk_forward_windows(
        index, train_period=pd.Timedelta(hours=8), test_period=pd.Timedelta(hours=4)
    )
    assert windows == []


def test_generate_windows_empty_index():
    windows = generate_walk_forward_windows(
        pd.DatetimeIndex([]), train_period=pd.Timedelta(hours=8), test_period=pd.Timedelta(hours=4)
    )
    assert windows == []


def test_windows_never_overlap():
    index = _index(100)
    windows = generate_walk_forward_windows(
        index, train_period=pd.Timedelta(hours=20), test_period=pd.Timedelta(hours=10)
    )
    assert len(windows) > 1
    for w in windows:
        assert w.train_start < w.train_end == w.test_start < w.test_end


def test_run_walk_forward_on_synthetic_data():
    df = generate_synthetic_ohlcv(n=500)
    definition = StrategyDefinition(
        name="ema_test",
        indicators=[{"name": "ema", "alias": "ema_fast", "params": {"period": 5}}],
        entry_conditions={"type": "comparison", "left": "close", "op": "gt", "right": "ema_fast"},
        exit_conditions={"type": "comparison", "left": "close", "op": "lt", "right": "ema_fast"},
        risk_management=RiskManagement(stop_loss_pct=0.05, take_profit_pct=0.1),
    )

    results = run_walk_forward(
        definition,
        df,
        train_period=pd.Timedelta(days=10),
        test_period=pd.Timedelta(days=3),
        initial_capital=10_000.0,
        fee_pct=0.001,
    )

    assert len(results) > 0
    for r in results:
        assert r.window.test_start == r.window.train_end
        assert r.train_result.strategy_name == "ema_test"
        assert r.test_result.strategy_name == "ema_test"
        assert r.train_result.initial_capital == 10_000.0
