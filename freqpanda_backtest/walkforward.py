"""Walk-forward window splitting and execution.

Phase 3 delivers the *splitting and running* infrastructure: cut the
dataset into successive, non-overlapping train/test windows and run
`backtest()` with a single, fixed strategy definition on each. Optimizing
the strategy's parameters per train window (the actual point of walk-forward
validation) is phase 4's job -- it slots in between window generation and
the test-window backtest here, e.g.:

    for window in generate_walk_forward_windows(df.index, train_period, test_period):
        train_df = df[(df.index >= window.train_start) & (df.index < window.train_end)]
        tuned_definition = optimize(definition, train_df)   # phase 4
        test_df = df[(df.index >= window.test_start) & (df.index < window.test_end)]
        result = backtest(tuned_definition, test_df, ...)

`run_walk_forward` below runs the *same* definition on both the train and
test slice of each window (no tuning), which is still useful right now: it
tells you whether a strategy's train-window performance is at all
predictive of its test-window performance before any optimization is
layered on top.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from freqpanda_strategy import StrategyDefinition

from .backtest import backtest
from .result import BacktestResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WalkForwardWindow:
    """Half-open intervals ([start, end)) so train and test never overlap:
    the candle at exactly `train_end`/`test_start` belongs to the test
    window, not both.
    """

    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


@dataclass(frozen=True)
class WalkForwardResult:
    window: WalkForwardWindow
    train_result: BacktestResult
    test_result: BacktestResult


def generate_walk_forward_windows(
    index: pd.DatetimeIndex,
    train_period: pd.Timedelta,
    test_period: pd.Timedelta,
    step: Optional[pd.Timedelta] = None,
    anchored: bool = False,
) -> List[WalkForwardWindow]:
    """Slice `index`'s time range into successive train/test windows.

    `step` defaults to `test_period` (each window's test slice picks up
    exactly where the previous one left off). With `anchored=False`
    (default) the train window itself slides forward by `step` each time,
    always spanning `train_period` ("rolling"). With `anchored=True` the
    train window's start stays fixed at the data's start and only its end
    grows by `step` each time ("expanding").
    """
    if len(index) == 0:
        return []
    step = step if step is not None else test_period

    data_start, data_end = index[0], index[-1]
    windows: List[WalkForwardWindow] = []

    train_start = data_start
    train_end = data_start + train_period
    while True:
        test_start = train_end
        test_end = test_start + test_period
        if test_end > data_end:
            break
        windows.append(WalkForwardWindow(train_start, train_end, test_start, test_end))
        if anchored:
            train_end = train_end + step
        else:
            train_start = train_start + step
            train_end = train_start + train_period

    return windows


def run_walk_forward(
    definition: StrategyDefinition,
    df: pd.DataFrame,
    train_period: pd.Timedelta,
    test_period: pd.Timedelta,
    step: Optional[pd.Timedelta] = None,
    anchored: bool = False,
    **backtest_kwargs,
) -> List[WalkForwardResult]:
    """Run `backtest()` with `definition` (unchanged) on both the train and
    test slice of every walk-forward window. Windows whose train or test
    slice ends up empty (possible at the edges of sparse/gappy data) are
    skipped with a warning rather than producing a meaningless result.
    """
    windows = generate_walk_forward_windows(df.index, train_period, test_period, step, anchored)
    results: List[WalkForwardResult] = []

    for window in windows:
        train_df = df[(df.index >= window.train_start) & (df.index < window.train_end)]
        test_df = df[(df.index >= window.test_start) & (df.index < window.test_end)]
        if train_df.empty or test_df.empty:
            logger.warning("Skipping empty walk-forward window %s", window)
            continue

        train_result = backtest(definition, train_df, **backtest_kwargs)
        test_result = backtest(definition, test_df, **backtest_kwargs)
        results.append(WalkForwardResult(window=window, train_result=train_result, test_result=test_result))

    return results
