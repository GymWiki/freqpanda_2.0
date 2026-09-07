"""Run many strategy variants against the same OHLCV data in parallel.

`backtest()` is a pure function of (definition, df, capital, fees) with no
shared mutable state, which makes it embarrassingly parallel across
independent CPU processes -- the practical lever for "thousands of
variants" once a single run is already as fast as phase 3 can make it (see
the README benchmark: the per-candle interpreter loop, not the metrics
math, dominates a single run's time, so more throughput comes from running
more variants at once, not from further micro-optimizing one run).

The OHLCV DataFrame is sent to each worker process exactly once, at pool
startup (`initializer`/`initargs`), instead of once per task -- with
thousands of variants sharing one (potentially large) DataFrame, that
avoids re-pickling it on every submitted job.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from typing import List, Optional, Sequence

import pandas as pd

from freqpanda_strategy import StrategyDefinition

from .backtest import backtest
from .result import BacktestResult

_worker_df: Optional[pd.DataFrame] = None
_worker_kwargs: dict = {}


def _init_worker(df: pd.DataFrame, backtest_kwargs: dict) -> None:
    global _worker_df, _worker_kwargs
    _worker_df = df
    _worker_kwargs = backtest_kwargs


def _run_one(definition: StrategyDefinition) -> BacktestResult:
    return backtest(definition, _worker_df, **_worker_kwargs)


def run_backtests_parallel(
    definitions: Sequence[StrategyDefinition],
    df: pd.DataFrame,
    max_workers: Optional[int] = None,
    **backtest_kwargs,
) -> List[BacktestResult]:
    """Run `backtest(definition, df, **backtest_kwargs)` for every
    `definition`, spread across a process pool. Results are returned in the
    same order as `definitions`.
    """
    with ProcessPoolExecutor(
        max_workers=max_workers, initializer=_init_worker, initargs=(df, backtest_kwargs)
    ) as executor:
        return list(executor.map(_run_one, definitions))
