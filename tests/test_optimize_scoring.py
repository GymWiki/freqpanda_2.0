import math

import pandas as pd
import pytest

from freqpanda_backtest import BacktestResult, TradingCosts
from freqpanda_optimize.scoring import score_from_result


def _result(**overrides) -> BacktestResult:
    defaults = dict(
        strategy_name="s",
        initial_capital=10_000.0,
        final_capital=11_000.0,
        total_return_pct=0.10,
        total_return_abs=1_000.0,
        sharpe_ratio=1.5,
        sortino_ratio=2.0,
        max_drawdown_pct=0.05,
        max_drawdown_duration=pd.Timedelta(hours=3),
        num_trades=4,
        win_rate=0.75,
        avg_win_pct=0.03,
        avg_loss_pct=-0.01,
        profit_factor=3.0,
        trades=[],
        equity_curve=pd.Series([10_000.0, 11_000.0]),
        costs=TradingCosts(),
    )
    defaults.update(overrides)
    return BacktestResult(**defaults)


def test_score_from_result_by_attribute_name():
    result = _result(sharpe_ratio=1.23)
    assert score_from_result(result, "sharpe_ratio") == pytest.approx(1.23)


def test_score_from_result_by_callable():
    result = _result(sharpe_ratio=2.0, max_drawdown_pct=0.2)
    composite = lambda r: r.sharpe_ratio - r.max_drawdown_pct
    assert score_from_result(result, composite) == pytest.approx(1.8)


def test_score_from_result_nan_becomes_worst_score():
    result = _result(sharpe_ratio=float("nan"))
    score = score_from_result(result, "sharpe_ratio")
    assert score == float("-inf")


def test_score_from_result_infinite_profit_factor_is_kept():
    result = _result(profit_factor=float("inf"))
    assert score_from_result(result, "profit_factor") == float("inf")


def test_score_from_result_unknown_metric_raises():
    result = _result()
    with pytest.raises(ValueError, match="Unknown metric"):
        score_from_result(result, "not_a_real_field")
