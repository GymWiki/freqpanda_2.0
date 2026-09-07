"""Parameter optimization via Optuna, validated with walk-forward windows
rather than a single train/test split.

Three layers, from the ground up:

  - `optimize_single_split`: one Optuna study on a train slice, then one
    out-of-sample backtest of the best trial on a held-out test slice.
    This is the building block; on its own it's exactly the "single
    train/test split" the phase-4 brief says not to rely on alone.
  - `optimize`: runs `optimize_single_split` on every window produced by
    phase 3's `generate_walk_forward_windows` (rolling or anchored), so the
    optimizer is validated across several distinct train/test periods
    instead of one. This is the main entrypoint.
  - `refit_on_full_history`: once walk-forward validation (via `optimize`)
    shows the approach isn't just overfitting to one period, this does one
    final Optuna study over *all* available data to produce the parameter
    set to actually deploy. There is no held-out test slice here by
    construction (there's no more unseen data left) -- it is a deployment
    step, not a validation step, and its `BacktestResult` is in-sample by
    definition. Don't read it as evidence the strategy works; `optimize`'s
    per-window out-of-sample results are that evidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import optuna
import pandas as pd

from freqpanda_backtest import BacktestResult, backtest
from freqpanda_backtest.walkforward import WalkForwardWindow, generate_walk_forward_windows
from freqpanda_strategy import StrategyDefinition

from .scoring import MetricLike, score_from_result
from .search_space import build_search_space, materialize_definition, suggest_params

logger = logging.getLogger(__name__)

optuna.logging.set_verbosity(optuna.logging.WARNING)


@dataclass(frozen=True)
class WindowOptimizationResult:
    window: Optional[WalkForwardWindow]  # None when produced by optimize_single_split directly
    metric: MetricLike
    best_params: dict
    best_definition: StrategyDefinition
    in_sample_result: BacktestResult
    out_of_sample_result: BacktestResult
    study: optuna.Study

    @property
    def in_sample_score(self) -> float:
        return score_from_result(self.in_sample_result, self.metric)

    @property
    def out_of_sample_score(self) -> float:
        return score_from_result(self.out_of_sample_result, self.metric)


def optimize_single_split(
    definition: StrategyDefinition,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    metric: MetricLike = "sharpe_ratio",
    n_trials: int = 50,
    timeout: Optional[float] = None,
    sampler: Optional[optuna.samplers.BaseSampler] = None,
    backtest_kwargs: Optional[dict] = None,
    window: Optional[WalkForwardWindow] = None,
) -> WindowOptimizationResult:
    """Optimize `definition`'s tunable (`ParamRange`) indicator parameters
    against `train_df`, then evaluate the best trial once on `test_df`
    (never touched during the search). `n_trials`/`timeout` bound the
    search -- `study.optimize` returns once either is hit, so this always
    terminates, which matters once it's called from a phase-5 job queue.
    """
    backtest_kwargs = backtest_kwargs or {}
    search_space = build_search_space(definition)

    def objective(trial: optuna.Trial) -> float:
        values = suggest_params(trial, search_space)
        candidate = materialize_definition(definition, values)
        result = backtest(candidate, train_df, **backtest_kwargs)
        return score_from_result(result, metric)

    study = optuna.create_study(direction="maximize", sampler=sampler or optuna.samplers.TPESampler())
    study.optimize(objective, n_trials=n_trials, timeout=timeout)

    best_definition = materialize_definition(definition, study.best_params)
    in_sample_result = backtest(best_definition, train_df, **backtest_kwargs)
    out_of_sample_result = backtest(best_definition, test_df, **backtest_kwargs)

    return WindowOptimizationResult(
        window=window,
        metric=metric,
        best_params=study.best_params,
        best_definition=best_definition,
        in_sample_result=in_sample_result,
        out_of_sample_result=out_of_sample_result,
        study=study,
    )


@dataclass(frozen=True)
class OptimizationResult:
    metric: MetricLike
    windows: List[WindowOptimizationResult]

    def summary(self) -> pd.DataFrame:
        """One row per walk-forward window: its date range plus in-sample
        and out-of-sample score -- the table to eyeball for overfitting
        (out-of-sample consistently far below in-sample means the search
        is fitting noise in the train window, not a real edge).
        """
        rows = []
        for w in self.windows:
            rows.append(
                {
                    "train_start": w.window.train_start if w.window else None,
                    "train_end": w.window.train_end if w.window else None,
                    "test_start": w.window.test_start if w.window else None,
                    "test_end": w.window.test_end if w.window else None,
                    "in_sample_score": w.in_sample_score,
                    "out_of_sample_score": w.out_of_sample_score,
                    "num_trades_test": w.out_of_sample_result.num_trades,
                }
            )
        return pd.DataFrame(rows)

    def mean_in_sample_score(self) -> float:
        return float(pd.Series([w.in_sample_score for w in self.windows]).mean())

    def mean_out_of_sample_score(self) -> float:
        return float(pd.Series([w.out_of_sample_score for w in self.windows]).mean())


def optimize(
    definition: StrategyDefinition,
    df: pd.DataFrame,
    train_period: pd.Timedelta,
    test_period: pd.Timedelta,
    metric: MetricLike = "sharpe_ratio",
    n_trials: int = 50,
    timeout: Optional[float] = None,
    step: Optional[pd.Timedelta] = None,
    anchored: bool = False,
    sampler: Optional[optuna.samplers.BaseSampler] = None,
    backtest_kwargs: Optional[dict] = None,
) -> OptimizationResult:
    """Walk-forward parameter optimization: split `df` into successive
    train/test windows (phase 3's `generate_walk_forward_windows`), and run
    `optimize_single_split` independently on each. `n_trials`/`timeout`
    apply *per window*, so the total budget is roughly
    `len(windows) * n_trials` trials (or `len(windows) * timeout` seconds).

    Raises `ValueError` if the windowing produces zero windows (`df`
    shorter than one `train_period + test_period`) -- silently returning an
    empty result would be easy to miss and read as "the strategy has no
    edge" instead of "the config doesn't fit the data".
    """
    windows = generate_walk_forward_windows(df.index, train_period, test_period, step, anchored)
    if not windows:
        raise ValueError(
            "No walk-forward windows fit in the given data range; shorten "
            "train_period/test_period or provide more data."
        )

    window_results: List[WindowOptimizationResult] = []
    for window in windows:
        train_df = df[(df.index >= window.train_start) & (df.index < window.train_end)]
        test_df = df[(df.index >= window.test_start) & (df.index < window.test_end)]
        if train_df.empty or test_df.empty:
            logger.warning("Skipping empty walk-forward window %s", window)
            continue

        window_results.append(
            optimize_single_split(
                definition,
                train_df,
                test_df,
                metric=metric,
                n_trials=n_trials,
                timeout=timeout,
                sampler=sampler,
                backtest_kwargs=backtest_kwargs,
                window=window,
            )
        )

    return OptimizationResult(metric=metric, windows=window_results)


def refit_on_full_history(
    definition: StrategyDefinition,
    df: pd.DataFrame,
    metric: MetricLike = "sharpe_ratio",
    n_trials: int = 50,
    timeout: Optional[float] = None,
    sampler: Optional[optuna.samplers.BaseSampler] = None,
    backtest_kwargs: Optional[dict] = None,
) -> WindowOptimizationResult:
    """One final Optuna study over *all* of `df` -- the parameter set to
    actually deploy, once `optimize()` has shown the search process
    generalizes. `in_sample_result` and `out_of_sample_result` are
    identical here by construction (both are `df`): there is no more
    unseen data to hold out, so this step provides no overfitting evidence
    of its own.
    """
    return optimize_single_split(
        definition,
        df,
        df,
        metric=metric,
        n_trials=n_trials,
        timeout=timeout,
        sampler=sampler,
        backtest_kwargs=backtest_kwargs,
    )
