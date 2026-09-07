import pandas as pd
import pytest

from freqpanda_optimize.optimize import optimize, optimize_single_split, refit_on_full_history
from freqpanda_strategy import IndicatorConfig, ParamRange, RiskManagement, StrategyDefinition


def _tunable_ema_definition():
    return StrategyDefinition(
        name="ema_tunable",
        indicators=[
            IndicatorConfig(
                name="ema", alias="ema_fast", params={"period": ParamRange(default=8, min=5, max=12, step=1)}
            ),
            IndicatorConfig(
                name="ema", alias="ema_slow", params={"period": ParamRange(default=25, min=20, max=30, step=1)}
            ),
        ],
        entry_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_above", "right": "ema_slow"},
        exit_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_below", "right": "ema_slow"},
        risk_management=RiskManagement(stop_loss_pct=0.03, take_profit_pct=0.08),
    )


def test_optimize_single_split_returns_best_params_within_bounds(synthetic_ohlcv):
    n = len(synthetic_ohlcv)
    train_df = synthetic_ohlcv.iloc[: n // 2]
    test_df = synthetic_ohlcv.iloc[n // 2 :]

    result = optimize_single_split(
        _tunable_ema_definition(), train_df, test_df, metric="sharpe_ratio", n_trials=5
    )

    assert 5 <= result.best_params["ema_fast.period"] <= 12
    assert 20 <= result.best_params["ema_slow.period"] <= 30
    assert result.best_definition.indicators[0].params["period"] == result.best_params["ema_fast.period"]
    assert result.in_sample_result.strategy_name == "ema_tunable"
    assert result.out_of_sample_result.strategy_name == "ema_tunable"
    assert isinstance(result.in_sample_score, float)
    assert isinstance(result.out_of_sample_score, float)


def test_optimize_walk_forward_produces_one_result_per_window(synthetic_ohlcv):
    result = optimize(
        _tunable_ema_definition(),
        synthetic_ohlcv,
        train_period=pd.Timedelta(days=10),
        test_period=pd.Timedelta(days=3),
        metric="sharpe_ratio",
        n_trials=3,
    )

    assert len(result.windows) > 0
    for w in result.windows:
        assert w.window is not None
        assert w.window.test_start == w.window.train_end

    summary = result.summary()
    assert len(summary) == len(result.windows)
    assert {"in_sample_score", "out_of_sample_score"} <= set(summary.columns)
    assert isinstance(result.mean_in_sample_score(), float)
    assert isinstance(result.mean_out_of_sample_score(), float)


def test_optimize_raises_when_no_windows_fit(synthetic_ohlcv):
    with pytest.raises(ValueError, match="No walk-forward windows"):
        optimize(
            _tunable_ema_definition(),
            synthetic_ohlcv,
            train_period=pd.Timedelta(days=1000),
            test_period=pd.Timedelta(days=100),
            n_trials=2,
        )


def test_refit_on_full_history_has_identical_in_and_out_of_sample(synthetic_ohlcv):
    result = refit_on_full_history(_tunable_ema_definition(), synthetic_ohlcv, n_trials=3)
    assert result.window is None
    assert result.in_sample_result.final_capital == result.out_of_sample_result.final_capital
