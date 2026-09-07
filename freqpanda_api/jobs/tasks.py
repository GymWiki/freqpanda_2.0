"""The functions RQ workers actually run. Each one is a self-contained unit
of work: it opens its own DB connection (a worker is a separate process
from the API, so it can't reuse a request-scoped connection), does
everything through phases 1-4's own public functions, writes the result,
and updates the job's status -- nothing here reimplements interpreter,
backtest, or optimization logic.

Deliberately reads OHLCV via `freqpanda_data.fetch_ohlcv_dataframe` (phase
2's storage) rather than fetching from the exchange inline: phase 2's
pipeline is the thing responsible for keeping candle data fresh (its own
cron/schedule, own rate-limit handling), and a job here should be fast and
deterministic, not make a live exchange call as a side effect. A range with
no stored data fails the job with a clear message instead of silently
reaching out to CCXT.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

import pandas as pd

from freqpanda_backtest import backtest
from freqpanda_data.db import fetch_ohlcv_dataframe
from freqpanda_data.db import get_connection as get_data_connection
from freqpanda_optimize import WindowOptimizationResult, optimize, refit_on_full_history

from ..config import get_settings
from ..repositories import jobs as jobs_repo
from ..repositories import results as results_repo
from ..repositories import strategies as strategies_repo


def _parse_dt(value: Optional[str]) -> Optional[dt.datetime]:
    return dt.datetime.fromisoformat(value) if value else None


def _load_ohlcv(conn, payload: Dict[str, Any]) -> pd.DataFrame:
    df = fetch_ohlcv_dataframe(
        conn,
        exchange=payload["exchange"],
        symbol=payload["symbol"],
        timeframe=payload["timeframe"],
        start=_parse_dt(payload.get("start")),
        end=_parse_dt(payload.get("end")),
    )
    if df.empty:
        raise RuntimeError(
            f"No stored OHLCV data for {payload['exchange']}/{payload['symbol']}/{payload['timeframe']} "
            "in the requested range. Run the phase-2 data pipeline for this pair first."
        )
    return df


def _backtest_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "initial_capital": payload.get("initial_capital", 10_000.0),
        "fee_pct": payload.get("fee_pct", 0.001),
        "slippage_pct": payload.get("slippage_pct", 0.0),
    }


def run_backtest_job(job_id: str) -> None:
    conn = get_data_connection(get_settings().database_url)
    try:
        job = jobs_repo.get_job_unscoped(conn, job_id)
        if job is None:
            return
        jobs_repo.mark_running(conn, job_id)
        try:
            strategy = strategies_repo.get_strategy(conn, job.strategy_id, job.created_by)
            if strategy is None:
                raise RuntimeError(f"Strategy {job.strategy_id} not found")

            df = _load_ohlcv(conn, job.payload)
            result = backtest(strategy.definition, df, **_backtest_kwargs(job.payload))

            results_repo.save_backtest_result(conn, job_id, strategy.id, result)
            jobs_repo.mark_completed(conn, job_id)
        except Exception as exc:
            jobs_repo.mark_failed(conn, job_id, str(exc))
            raise
    finally:
        conn.close()


def _window_to_dict(w: WindowOptimizationResult) -> Dict[str, Any]:
    return {
        "train_start": w.window.train_start.isoformat() if w.window else None,
        "train_end": w.window.train_end.isoformat() if w.window else None,
        "test_start": w.window.test_start.isoformat() if w.window else None,
        "test_end": w.window.test_end.isoformat() if w.window else None,
        "best_params": w.best_params,
        "in_sample_score": w.in_sample_score,
        "out_of_sample_score": w.out_of_sample_score,
        "in_sample_metrics": w.in_sample_result.metrics_dict(),
        "out_of_sample_metrics": w.out_of_sample_result.metrics_dict(),
    }


def run_optimization_job(job_id: str) -> None:
    conn = get_data_connection(get_settings().database_url)
    try:
        job = jobs_repo.get_job_unscoped(conn, job_id)
        if job is None:
            return
        jobs_repo.mark_running(conn, job_id)
        try:
            strategy = strategies_repo.get_strategy(conn, job.strategy_id, job.created_by)
            if strategy is None:
                raise RuntimeError(f"Strategy {job.strategy_id} not found")

            payload = job.payload
            df = _load_ohlcv(conn, payload)
            metric = payload.get("metric", "sharpe_ratio")
            n_trials = payload.get("n_trials", 50)
            timeout = payload.get("timeout_seconds")
            backtest_kwargs = _backtest_kwargs(payload)

            opt_result = optimize(
                strategy.definition,
                df,
                train_period=pd.Timedelta(days=payload["train_period_days"]),
                test_period=pd.Timedelta(days=payload["test_period_days"]),
                metric=metric,
                n_trials=n_trials,
                timeout=timeout,
                backtest_kwargs=backtest_kwargs,
            )
            final = refit_on_full_history(
                strategy.definition,
                df,
                metric=metric,
                n_trials=n_trials,
                timeout=timeout,
                backtest_kwargs=backtest_kwargs,
            )

            windows: List[Dict[str, Any]] = [_window_to_dict(w) for w in opt_result.windows]
            results_repo.save_optimization_result(
                conn,
                job_id,
                strategy.id,
                metric,
                windows,
                opt_result.mean_in_sample_score(),
                opt_result.mean_out_of_sample_score(),
                final.best_params,
                final.best_definition.model_dump(mode="json"),
            )
            jobs_repo.mark_completed(conn, job_id)
        except Exception as exc:
            jobs_repo.mark_failed(conn, job_id, str(exc))
            raise
    finally:
        conn.close()
