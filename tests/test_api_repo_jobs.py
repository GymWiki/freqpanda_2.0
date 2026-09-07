import datetime as dt
from unittest.mock import MagicMock

from freqpanda_api.repositories.jobs import (
    create_job,
    get_job,
    get_job_unscoped,
    list_jobs,
    mark_completed,
    mark_failed,
    mark_running,
)


def _mock_conn_with_cursor():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


def _row(job_id, job_type="backtest", status="pending", strategy_id="strat_1", payload=None, error=None):
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    return (job_id, job_type, status, strategy_id, payload or {"symbol": "BTC/USDT"}, error, "owner-hash", now, None, None)


def test_create_job_returns_pending_record():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = _row("job_1")

    job = create_job(conn, "backtest", "strat_1", {"symbol": "BTC/USDT"}, "owner-hash")

    assert job.id == "job_1"
    assert job.status == "pending"
    assert job.job_type == "backtest"
    conn.commit.assert_called_once()


def test_get_job_scoped_returns_none_for_other_owner():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = None
    assert get_job(conn, "job_1", "someone-else") is None


def test_get_job_unscoped_used_by_worker():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = _row("job_1")
    job = get_job_unscoped(conn, "job_1")
    assert job.id == "job_1"
    sql, params = cursor.execute.call_args[0]
    assert params == ("job_1",)


def test_list_jobs_filters_by_strategy_type_and_owner():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchall.return_value = [_row("job_1"), _row("job_2")]
    jobs = list_jobs(conn, "strat_1", "backtest", "owner-hash")
    assert [j.id for j in jobs] == ["job_1", "job_2"]
    sql, params = cursor.execute.call_args[0]
    assert params == ("strat_1", "backtest", "owner-hash")


def test_mark_running_updates_status_and_started_at():
    conn, cursor = _mock_conn_with_cursor()
    mark_running(conn, "job_1")
    sql, params = cursor.execute.call_args[0]
    assert "running" in sql
    assert params == ("job_1",)
    conn.commit.assert_called_once()


def test_mark_completed_updates_status():
    conn, cursor = _mock_conn_with_cursor()
    mark_completed(conn, "job_1")
    sql, params = cursor.execute.call_args[0]
    assert "completed" in sql


def test_mark_failed_stores_error_message():
    conn, cursor = _mock_conn_with_cursor()
    mark_failed(conn, "job_1", "boom")
    sql, params = cursor.execute.call_args[0]
    assert params == ("boom", "job_1")
