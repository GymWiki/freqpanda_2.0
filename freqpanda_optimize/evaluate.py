"""Batch-evaluate a list of strategy definitions (generated, optimized, or
both) and rank them by a chosen metric.

Reuses phase 3's `run_backtests_parallel` directly -- a plain backtest of a
generated variant needs no special handling, since a `ParamRange` on an
indicator parameter already resolves to its `.default` inside
`run_strategy` with no extra step required here.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import pandas as pd

from freqpanda_backtest import BacktestResult, run_backtests_parallel
from freqpanda_strategy import StrategyDefinition

from .scoring import MetricLike, score_from_result


def evaluate_variants(
    variants: Sequence[StrategyDefinition],
    df: pd.DataFrame,
    metric: MetricLike = "sharpe_ratio",
    max_workers: Optional[int] = None,
    **backtest_kwargs,
) -> List[Tuple[StrategyDefinition, BacktestResult]]:
    """Backtest every variant against the same `df` (in parallel, see
    `freqpanda_backtest.run_backtests_parallel`) and return
    `(definition, result)` pairs sorted best-first by `metric`. A variant
    whose metric is undefined (e.g. it produced zero trades) is scored as
    the worst possible value by `score_from_result` and so sorts last,
    rather than raising or corrupting the ordering with a raw NaN
    comparison.
    """
    results = run_backtests_parallel(list(variants), df, max_workers=max_workers, **backtest_kwargs)
    paired = list(zip(variants, results))
    paired.sort(key=lambda pair: score_from_result(pair[1], metric), reverse=True)
    return paired
