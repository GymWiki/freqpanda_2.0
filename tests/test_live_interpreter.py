"""The core "no drift between backtest and live" guarantee: feeding the
same OHLCV data to `LivePositionTracker` one candle at a time must produce
the exact same trades `run_strategy` produces from a single call over the
whole DataFrame. See `freqpanda_execution/live_interpreter.py`'s module
docstring -- this test is the actual proof, not just a comment claiming it.
"""
import random

import pandas as pd
import pytest

from freqpanda_execution.live_interpreter import LivePositionTracker, latest_signal
from freqpanda_strategy import IndicatorConfig, RiskManagement, StrategyDefinition, run_strategy


def _random_walk_ohlcv(n: int, seed: int, start_price: float = 100.0) -> pd.DataFrame:
    rng = random.Random(seed)
    opens, highs, lows, closes = [], [], [], []
    price = start_price
    for _ in range(n):
        open_ = price
        close = max(1.0, open_ * (1 + rng.uniform(-0.03, 0.03)))
        high = max(open_, close) * (1 + rng.uniform(0, 0.01))
        low = min(open_, close) * (1 - rng.uniform(0, 0.01))
        opens.append(open_)
        highs.append(high)
        lows.append(low)
        closes.append(close)
        price = close
    index = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1.0] * n},
        index=index,
    )


def _ema_crossover_definition() -> StrategyDefinition:
    return StrategyDefinition(
        name="parity_test_ema_crossover",
        indicators=[
            IndicatorConfig(name="ema", alias="ema_fast", params={"period": 5}),
            IndicatorConfig(name="ema", alias="ema_slow", params={"period": 20}),
            IndicatorConfig(name="rsi", alias="rsi", params={"period": 14}),
        ],
        entry_conditions={
            "type": "logical",
            "op": "and",
            "conditions": [
                {"type": "comparison", "left": "ema_fast", "op": "crosses_above", "right": "ema_slow"},
                {"type": "comparison", "left": "rsi", "op": "lt", "right": 70},
            ],
        },
        exit_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_below", "right": "ema_slow"},
        risk_management=RiskManagement(stop_loss_pct=0.05, take_profit_pct=0.08, trailing_stop_pct=0.03),
    )


def _run_live(definition: StrategyDefinition, df: pd.DataFrame):
    """Mirrors what `freqpanda_execution.bot.Bot._on_candle_close` does,
    minus everything unrelated to the trade decisions themselves (no
    broker, no risk middleware, no persistence): grow the visible history
    one candle at a time and record every entry/exit the tracker reports.
    """
    tracker = LivePositionTracker(definition.risk_management)
    trades = []
    open_entry = None

    for i in range(1, len(df) + 1):
        window = df.iloc[:i]
        snapshot = latest_signal(definition, window)
        action = tracker.process(snapshot)
        if action is None:
            continue
        if action.kind == "enter":
            open_entry = (snapshot.timestamp, action.price)
        else:
            entry_time, entry_price = open_entry
            trades.append(
                {
                    "entry_time": entry_time,
                    "entry_price": entry_price,
                    "exit_time": snapshot.timestamp,
                    "exit_price": action.price,
                    "exit_reason": action.reason,
                }
            )
            open_entry = None
    return trades


def _backtest_trades_as_dicts(definition: StrategyDefinition, df: pd.DataFrame):
    return [
        {
            "entry_time": t.entry_time,
            "entry_price": t.entry_price,
            "exit_time": t.exit_time,
            "exit_price": t.exit_price,
            "exit_reason": t.exit_reason,
        }
        for t in run_strategy(definition, df)
    ]


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_live_tracker_matches_backtest_trade_for_trade(seed):
    definition = _ema_crossover_definition()
    df = _random_walk_ohlcv(n=300, seed=seed)

    backtest_trades = _backtest_trades_as_dicts(definition, df)
    live_trades = _run_live(definition, df)

    assert live_trades == backtest_trades
    # A meaningful parity claim needs at least a handful of real trades to
    # compare, not an empty list both sides trivially agree on.
    assert len(backtest_trades) >= 3


def test_live_tracker_matches_backtest_with_no_exit_conditions_and_raw_ohlcv():
    """A second definition shape -- no indicators, no exit_conditions, so
    the only exits come from stop_loss/take_profit/trailing_stop -- to make
    sure the parity claim isn't an artifact of one particular strategy shape.
    """
    definition = StrategyDefinition(
        name="parity_test_raw_ohlcv",
        indicators=[],
        entry_conditions={"type": "comparison", "left": "close", "op": "gt", "right": "open"},
        exit_conditions=None,
        risk_management=RiskManagement(stop_loss_pct=0.02, take_profit_pct=0.03),
    )
    df = _random_walk_ohlcv(n=150, seed=42)

    backtest_trades = _backtest_trades_as_dicts(definition, df)
    live_trades = _run_live(definition, df)

    assert live_trades == backtest_trades
    assert len(backtest_trades) >= 3
