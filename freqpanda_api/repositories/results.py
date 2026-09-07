"""Persists and reads back backtest/optimization results.

Writes take the phase-3/phase-4 result objects directly and call their own
serialization methods (`BacktestResult.metrics_dict()` etc.,
`OptimizationResult.summary()`) rather than re-deriving that shape here --
those methods exist precisely so this layer doesn't have to know anything
about equity curves or Optuna studies.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json

from freqpanda_backtest import BacktestResult


def _json_safe(value: Any) -> Any:
    """Postgres' json/jsonb types are strict RFC 8259 JSON, which has no
    representation for Infinity/-Infinity/NaN -- but phase 3's metrics
    legitimately produce `float('inf')` (e.g. profit_factor with zero
    losing trades) and `float('nan')` (e.g. Sharpe with no variance).
    Python's `json.dumps` happily emits the non-standard `Infinity`/`NaN`
    tokens for those, which Postgres then rejects outright. Recursively
    replace any non-finite float with `None` (SQL NULL) before it reaches
    `Json(...)`, since that's the only value jsonb can actually store here.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def save_backtest_result(conn, job_id: str, strategy_id: str, result: BacktestResult) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into backtest_results (job_id, strategy_id, metrics, trades, equity_curve)
            values (%s, %s, %s, %s, %s)
            on conflict (job_id) do update set
                metrics = excluded.metrics, trades = excluded.trades, equity_curve = excluded.equity_curve
            """,
            (
                job_id,
                strategy_id,
                Json(_json_safe(result.metrics_dict())),
                Json(_json_safe(result.trade_records())),
                Json(_json_safe(result.equity_curve_records())),
            ),
        )
    conn.commit()


def get_backtest_result(conn, job_id: str) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "select metrics, trades, equity_curve, created_at from backtest_results where job_id = %s",
            (job_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    metrics, trades, equity_curve, created_at = row
    return {"metrics": metrics, "trades": trades, "equity_curve": equity_curve, "created_at": created_at}


def list_backtest_summaries(conn, strategy_id: str, created_by: str) -> List[Dict[str, Any]]:
    """One row per backtest job for `strategy_id`: job status/timing plus
    `metrics` (None until the job completes) -- deliberately omits the full
    trade list/equity curve, which is what `get_backtest_result` is for.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            select j.id, j.status, j.created_at, j.started_at, j.finished_at, j.error, r.metrics
            from jobs j
            left join backtest_results r on r.job_id = j.id
            where j.strategy_id = %s and j.job_type = 'backtest' and j.created_by = %s
            order by j.created_at desc
            """,
            (strategy_id, created_by),
        )
        rows = cur.fetchall()
    return [
        {
            "job_id": job_id,
            "status": status,
            "created_at": created_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "error": error,
            "metrics": metrics,
        }
        for job_id, status, created_at, started_at, finished_at, error, metrics in rows
    ]


def save_optimization_result(
    conn,
    job_id: str,
    strategy_id: str,
    metric: str,
    windows: List[Dict[str, Any]],
    mean_in_sample_score: float,
    mean_out_of_sample_score: float,
    final_params: Dict[str, Any],
    final_definition: Dict[str, Any],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into optimization_results
                (job_id, strategy_id, metric, windows, mean_in_sample_score,
                 mean_out_of_sample_score, final_params, final_definition)
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (job_id) do update set
                metric = excluded.metric, windows = excluded.windows,
                mean_in_sample_score = excluded.mean_in_sample_score,
                mean_out_of_sample_score = excluded.mean_out_of_sample_score,
                final_params = excluded.final_params, final_definition = excluded.final_definition
            """,
            (
                job_id,
                strategy_id,
                metric,
                Json(_json_safe(windows)),
                mean_in_sample_score,
                mean_out_of_sample_score,
                Json(_json_safe(final_params)),
                Json(_json_safe(final_definition)),
            ),
        )
    conn.commit()


def get_optimization_result(conn, job_id: str) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select metric, windows, mean_in_sample_score, mean_out_of_sample_score,
                   final_params, final_definition, created_at
            from optimization_results where job_id = %s
            """,
            (job_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    metric, windows, mean_is, mean_oos, final_params, final_definition, created_at = row
    return {
        "metric": metric,
        "windows": windows,
        "mean_in_sample_score": mean_is,
        "mean_out_of_sample_score": mean_oos,
        "final_params": final_params,
        "final_definition": final_definition,
        "created_at": created_at,
    }


def list_optimization_summaries(conn, strategy_id: str, created_by: str) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select j.id, j.status, j.created_at, j.started_at, j.finished_at, j.error,
                   r.mean_in_sample_score, r.mean_out_of_sample_score
            from jobs j
            left join optimization_results r on r.job_id = j.id
            where j.strategy_id = %s and j.job_type = 'optimization' and j.created_by = %s
            order by j.created_at desc
            """,
            (strategy_id, created_by),
        )
        rows = cur.fetchall()
    return [
        {
            "job_id": job_id,
            "status": status,
            "created_at": created_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "error": error,
            "mean_in_sample_score": mean_is,
            "mean_out_of_sample_score": mean_oos,
        }
        for job_id, status, created_at, started_at, finished_at, error, mean_is, mean_oos in rows
    ]
