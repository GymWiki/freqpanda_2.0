import pandas as pd

from freqpanda_optimize.evaluate import evaluate_variants
from freqpanda_strategy import RiskManagement, StrategyDefinition


def _ohlcv(closes):
    n = len(closes)
    index = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1.0] * n},
        index=index,
    )


def _definition(name, entry_threshold):
    return StrategyDefinition(
        name=name,
        indicators=[],
        entry_conditions={"type": "comparison", "left": "close", "op": "gt", "right": entry_threshold},
        exit_conditions={"type": "comparison", "left": "close", "op": "lt", "right": entry_threshold},
        risk_management=RiskManagement(stop_loss_pct=0.5, take_profit_pct=0.5),
    )


def _definition_with_exit_above(name, entry_threshold, exit_threshold):
    return StrategyDefinition(
        name=name,
        indicators=[],
        entry_conditions={"type": "comparison", "left": "close", "op": "gt", "right": entry_threshold},
        exit_conditions={"type": "comparison", "left": "close", "op": "gt", "right": exit_threshold},
        risk_management=RiskManagement(stop_loss_pct=0.5, take_profit_pct=0.5),
    )


def test_evaluate_variants_sorted_best_first():
    # close path: 100 -> 105 -> 110 -> 95 -> 130 -> 90
    df = _ohlcv([100, 105, 110, 95, 130, 90])

    # profitable: enters at 105, rides the dip to 95, exits at 130 (net win).
    profitable = _definition_with_exit_above("profitable", 100, 125)
    # losing: enters at 105, exits as soon as it dips (net loss).
    losing = _definition("losing", 100)
    # never triggers -> zero trades -> flat equity -> undefined (NaN) Sharpe.
    never_triggers = _definition("never_triggers", 1_000_000)

    ranked = evaluate_variants(
        [losing, never_triggers, profitable],
        df,
        metric="sharpe_ratio",
        max_workers=1,
        fee_pct=0.0,
    )

    names_in_order = [definition.name for definition, _ in ranked]
    assert names_in_order[0] == "profitable"
    assert names_in_order[-1] == "never_triggers"  # NaN metric always sorts last


def test_evaluate_variants_returns_matching_results():
    df = _ohlcv([100, 105, 95])
    definitions = [_definition("a", 100), _definition("b", 100)]
    ranked = evaluate_variants(definitions, df, metric="num_trades", max_workers=1)
    assert len(ranked) == 2
    for definition, result in ranked:
        assert result.strategy_name == definition.name
