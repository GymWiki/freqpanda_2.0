import pandas as pd
import pytest

from freqpanda_strategy import RiskManagement, StrategyDefinition, run_strategy
from freqpanda_strategy.loader import load_strategy_definition

EXAMPLES_DIR = "examples"


def _ohlcv(closes, highs=None, lows=None, opens=None, freq="1h"):
    n = len(closes)
    opens = opens or closes
    highs = highs or [max(o, c) for o, c in zip(opens, closes)]
    lows = lows or [min(o, c) for o, c in zip(opens, closes)]
    index = pd.date_range("2024-01-01", periods=n, freq=freq)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1.0] * n},
        index=index,
    )


def _definition(entry, exit_, risk):
    return StrategyDefinition(
        name="raw_ohlcv_test",
        indicators=[],
        entry_conditions=entry,
        exit_conditions=exit_,
        risk_management=RiskManagement(**risk),
    )


def test_entry_and_exit_signal_roundtrip():
    df = _ohlcv(closes=[100, 105, 105, 95])
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_={"type": "comparison", "left": "close", "op": "lt", "right": 100},
        risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},  # wide enough to not interfere
    )
    trades = run_strategy(definition, df)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.entry_price == 105
    assert trade.exit_price == 95
    assert trade.exit_reason == "exit_signal"
    assert trade.entry_time < trade.exit_time
    assert trade.pnl_pct == pytest.approx(95 / 105 - 1)


def test_stop_loss_triggers_on_low():
    df = _ohlcv(closes=[100, 105, 100], lows=[100, 105, 90])
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None,
        risk={"stop_loss_pct": 0.02, "take_profit_pct": 0.5},
    )
    trades = run_strategy(definition, df)
    assert len(trades) == 1
    assert trades[0].exit_reason == "stop_loss"
    assert trades[0].exit_price == pytest.approx(105 * 0.98)


def test_take_profit_triggers_on_high():
    df = _ohlcv(closes=[100, 105, 100], highs=[100, 105, 120])
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None,
        risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.05},
    )
    trades = run_strategy(definition, df)
    assert len(trades) == 1
    assert trades[0].exit_reason == "take_profit"
    assert trades[0].exit_price == pytest.approx(105 * 1.05)


def test_stop_loss_wins_over_take_profit_same_candle():
    # Same candle's range hits both the stop-loss and take-profit levels.
    df = _ohlcv(closes=[100, 105, 100], highs=[100, 105, 130], lows=[100, 105, 90])
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None,
        risk={"stop_loss_pct": 0.02, "take_profit_pct": 0.05},
    )
    trades = run_strategy(definition, df)
    assert trades[0].exit_reason == "stop_loss"


def test_trailing_stop():
    # Entry at 100, price rises to 120 (raising the trailing peak), then
    # drops enough from that peak to trigger the trailing stop even though
    # it never falls below the fixed stop-loss level.
    df = _ohlcv(
        closes=[90, 100, 120, 110],
        highs=[90, 100, 120, 110],
        lows=[90, 100, 118, 105],
    )
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 95},
        exit_=None,
        risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5, "trailing_stop_pct": 0.1},
    )
    trades = run_strategy(definition, df)
    assert len(trades) == 1
    assert trades[0].exit_reason == "trailing_stop"
    assert trades[0].exit_price == pytest.approx(120 * 0.9)


def test_open_position_at_end_is_not_returned():
    df = _ohlcv(closes=[100, 105, 106])
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None,
        risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    trades = run_strategy(definition, df)
    assert trades == []


def test_missing_ohlcv_column_raises():
    from freqpanda_strategy import StrategyValidationError

    df = pd.DataFrame({"close": [1, 2, 3]}, index=pd.date_range("2024-01-01", periods=3))
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 0},
        exit_=None,
        risk={"stop_loss_pct": 0.1, "take_profit_pct": 0.1},
    )
    with pytest.raises(StrategyValidationError):
        run_strategy(definition, df)


@pytest.mark.parametrize(
    "filename", ["ema_crossover.json", "rsi_mean_reversion.json"]
)
def test_example_strategies_run_against_synthetic_data(filename, synthetic_ohlcv):
    definition = load_strategy_definition(f"{EXAMPLES_DIR}/{filename}")
    trades = run_strategy(definition, synthetic_ohlcv)
    assert len(trades) > 0
    for trade in trades:
        assert trade.entry_time < trade.exit_time
        assert trade.exit_reason in (
            "stop_loss",
            "take_profit",
            "trailing_stop",
            "exit_signal",
        )
