import datetime as dt
from unittest.mock import MagicMock

import pandas as pd

from freqpanda_api.repositories.results import (
    _json_safe,
    get_backtest_result,
    get_optimization_result,
    list_backtest_summaries,
    list_optimization_summaries,
    save_backtest_result,
    save_optimization_result,
)
from freqpanda_backtest import TradingCosts
from freqpanda_backtest.result import BacktestResult


def _mock_conn_with_cursor():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


def _backtest_result():
    return BacktestResult(
        strategy_name="ema_test",
        initial_capital=10_000.0,
        final_capital=11_000.0,
        total_return_pct=0.10,
        total_return_abs=1_000.0,
        sharpe_ratio=1.2,
        sortino_ratio=1.5,
        max_drawdown_pct=0.05,
        max_drawdown_duration=pd.Timedelta(hours=3),
        num_trades=2,
        win_rate=1.0,
        avg_win_pct=0.05,
        avg_loss_pct=0.0,
        profit_factor=float("inf"),
        trades=[],
        equity_curve=pd.Series([10_000.0, 11_000.0], index=pd.date_range("2024-01-01", periods=2, freq="1h")),
        costs=TradingCosts(fee_pct=0.001),
    )


def test_json_safe_replaces_non_finite_floats_with_none():
    assert _json_safe(float("inf")) is None
    assert _json_safe(float("-inf")) is None
    assert _json_safe(float("nan")) is None
    assert _json_safe(1.5) == 1.5
    assert _json_safe({"a": float("inf"), "b": [1.0, float("nan"), {"c": float("-inf")}]}) == {
        "a": None,
        "b": [1.0, None, {"c": None}],
    }


def test_save_backtest_result_sanitizes_infinite_profit_factor_for_jsonb():
    # Postgres' json/jsonb columns are strict JSON and reject the
    # "Infinity" token json.dumps emits for float('inf') -- a real bug this
    # test pins down after it broke a live backtest with zero losing trades.
    conn, cursor = _mock_conn_with_cursor()
    result = _backtest_result()
    object.__setattr__(result, "profit_factor", float("inf"))

    save_backtest_result(conn, "job_1", "strat_1", result)

    _, _, metrics_json, _, _ = cursor.execute.call_args[0][1]
    assert metrics_json.adapted["profit_factor"] is None


def test_save_backtest_result_writes_all_three_json_blobs():
    conn, cursor = _mock_conn_with_cursor()
    result = _backtest_result()

    save_backtest_result(conn, "job_1", "strat_1", result)

    sql, params = cursor.execute.call_args[0]
    assert "insert into backtest_results" in sql
    job_id, strategy_id, metrics_json, trades_json, equity_json = params
    assert job_id == "job_1"
    assert strategy_id == "strat_1"
    assert metrics_json.adapted["strategy_name"] == "ema_test"
    conn.commit.assert_called_once()


def test_get_backtest_result_returns_none_when_missing():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = None
    assert get_backtest_result(conn, "job_missing") is None


def test_get_backtest_result_maps_row():
    conn, cursor = _mock_conn_with_cursor()
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    cursor.fetchone.return_value = ({"sharpe_ratio": 1.2}, [{"entry_price": 1}], [{"equity": 1}], now)

    result = get_backtest_result(conn, "job_1")

    assert result["metrics"]["sharpe_ratio"] == 1.2
    assert result["trades"] == [{"entry_price": 1}]


def test_list_backtest_summaries_joins_jobs_and_results():
    conn, cursor = _mock_conn_with_cursor()
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    cursor.fetchall.return_value = [("job_1", "completed", now, now, now, None, {"sharpe_ratio": 1.2})]

    summaries = list_backtest_summaries(conn, "strat_1", "owner-hash")

    assert summaries[0]["job_id"] == "job_1"
    assert summaries[0]["metrics"]["sharpe_ratio"] == 1.2


def test_save_and_get_optimization_result():
    conn, cursor = _mock_conn_with_cursor()
    save_optimization_result(
        conn,
        "job_1",
        "strat_1",
        "sharpe_ratio",
        windows=[{"train_start": "2024-01-01"}],
        mean_in_sample_score=1.5,
        mean_out_of_sample_score=1.2,
        final_params={"ema_fast.period": 10},
        final_definition={"name": "ema_test"},
    )
    conn.commit.assert_called_once()

    conn2, cursor2 = _mock_conn_with_cursor()
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    cursor2.fetchone.return_value = (
        "sharpe_ratio", [{"train_start": "2024-01-01"}], 1.5, 1.2, {"ema_fast.period": 10}, {"name": "ema_test"}, now
    )
    result = get_optimization_result(conn2, "job_1")
    assert result["metric"] == "sharpe_ratio"
    assert result["mean_in_sample_score"] == 1.5


def test_list_optimization_summaries_joins_jobs_and_results():
    conn, cursor = _mock_conn_with_cursor()
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    cursor.fetchall.return_value = [("job_1", "completed", now, now, now, None, 1.5, 1.2)]

    summaries = list_optimization_summaries(conn, "strat_1", "owner-hash")

    assert summaries[0]["mean_in_sample_score"] == 1.5
    assert summaries[0]["mean_out_of_sample_score"] == 1.2
