"""Turns a `BacktestResult` into a single number to maximize.

A metric is either the name of a `BacktestResult` attribute (e.g.
`"sharpe_ratio"`, `"sortino_ratio"`, `"total_return_pct"`, `"profit_factor"`)
or a callable `BacktestResult -> float` for a composite score, e.g.:

    def composite(result):
        return result.sharpe_ratio - 0.5 * result.max_drawdown_pct

Undefined results (NaN -- e.g. a parameter combination that produces zero
trades, so Sharpe/Sortino/profit-factor are undefined) are scored as the
worst possible value rather than propagated as NaN: Optuna's samplers and
`sorted()` both handle comparisons badly once NaN is in the mix, and "no
trades" or "no variance" should simply lose to every trial that produced a
real result, not crash the study.
"""
from __future__ import annotations

import math
from typing import Callable, Union

from freqpanda_backtest import BacktestResult

MetricLike = Union[str, Callable[[BacktestResult], float]]

WORST_SCORE = float("-inf")


def score_from_result(result: BacktestResult, metric: MetricLike) -> float:
    if callable(metric):
        value = metric(result)
    else:
        if not hasattr(result, metric):
            available = [f for f in vars(result) if not f.startswith("_")]
            raise ValueError(f"Unknown metric '{metric}'. Available fields: {sorted(available)}")
        value = getattr(result, metric)

    value = float(value)
    return WORST_SCORE if math.isnan(value) else value
