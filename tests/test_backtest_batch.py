import pandas as pd

from freqpanda_backtest.batch import run_backtests_parallel
from freqpanda_strategy import RiskManagement, StrategyDefinition


def _ohlcv(closes):
    n = len(closes)
    index = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1.0] * n},
        index=index,
    )


def _definition(name, threshold):
    return StrategyDefinition(
        name=name,
        indicators=[],
        entry_conditions={"type": "comparison", "left": "close", "op": "gt", "right": threshold},
        exit_conditions={"type": "comparison", "left": "close", "op": "lt", "right": threshold},
        risk_management=RiskManagement(stop_loss_pct=0.5, take_profit_pct=0.5),
    )


def test_run_backtests_parallel_returns_results_in_order():
    df = _ohlcv([100, 105, 105, 95])
    definitions = [_definition(f"strategy_{i}", threshold) for i, threshold in enumerate([90, 100, 110])]

    results = run_backtests_parallel(definitions, df, max_workers=2, fee_pct=0.0)

    assert [r.strategy_name for r in results] == ["strategy_0", "strategy_1", "strategy_2"]
    for r in results:
        assert r.initial_capital == 10_000.0
