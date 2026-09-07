"""Integration test for the actual queueing mechanism: enqueues a real job
through a real Redis instance via RQ, then runs an RQ `SimpleWorker` in
burst mode (processes everything currently queued, then stops -- no
background process needed) in this same test process, so the DB/repository
patches applied here stay in effect for the worker's execution too.

Needs a real `redis-server` on the machine (present in this sandbox); the
fixture starts one on a throwaway port so it never collides with a real
Redis instance the same host might be running.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest
import redis as redis_lib
from rq import Queue, SimpleWorker

from freqpanda_api.repositories.jobs import JobRecord
from freqpanda_api.repositories.strategies import StrategyRecord
from freqpanda_strategy import RiskManagement, StrategyDefinition

from conftest import generate_synthetic_ohlcv

REDIS_TEST_PORT = 6398


@pytest.fixture(scope="module")
def redis_connection():
    if shutil.which("redis-server") is None:
        pytest.skip("redis-server not available on this machine")

    proc = subprocess.Popen(
        ["redis-server", "--port", str(REDIS_TEST_PORT), "--save", "", "--appendonly", "no", "--daemonize", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    conn = redis_lib.Redis(host="localhost", port=REDIS_TEST_PORT)
    for _ in range(50):
        try:
            if conn.ping():
                break
        except redis_lib.exceptions.ConnectionError:
            pass
        time.sleep(0.1)
    else:
        proc.terminate()
        pytest.fail("redis-server did not start in time")

    yield conn

    proc.terminate()
    proc.wait(timeout=5)


def _ema_definition():
    return StrategyDefinition(
        name="ema_test",
        indicators=[
            {"name": "ema", "alias": "ema_fast", "params": {"period": 5}},
            {"name": "ema", "alias": "ema_slow", "params": {"period": 20}},
        ],
        entry_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_above", "right": "ema_slow"},
        exit_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_below", "right": "ema_slow"},
        risk_management=RiskManagement(stop_loss_pct=0.03, take_profit_pct=0.08),
    )


def test_enqueued_backtest_job_runs_and_completes(redis_connection):
    from freqpanda_api.jobs.tasks import run_backtest_job

    definition = _ema_definition()
    job_record = JobRecord(
        id="job_integration_1", job_type="backtest", status="pending", strategy_id="strat_1",
        payload={"exchange": "binance", "symbol": "BTC/USDT", "timeframe": "1h"},
        error=None, created_by="owner-hash", created_at=None, started_at=None, finished_at=None,
    )
    strategy_record = StrategyRecord(
        id="strat_1", name=definition.name, definition=definition,
        created_by="owner-hash", created_at=None, updated_at=None,
    )

    with patch("freqpanda_api.jobs.tasks.get_data_connection", return_value=MagicMock()), \
         patch("freqpanda_api.jobs.tasks.jobs_repo.get_job_unscoped", return_value=job_record), \
         patch("freqpanda_api.jobs.tasks.strategies_repo.get_strategy", return_value=strategy_record), \
         patch("freqpanda_api.jobs.tasks.fetch_ohlcv_dataframe", return_value=generate_synthetic_ohlcv(n=500)), \
         patch("freqpanda_api.jobs.tasks.jobs_repo.mark_running") as mock_running, \
         patch("freqpanda_api.jobs.tasks.jobs_repo.mark_completed") as mock_completed, \
         patch("freqpanda_api.jobs.tasks.results_repo.save_backtest_result") as mock_save:

        queue = Queue("test-queue", connection=redis_connection)
        rq_job = queue.enqueue(run_backtest_job, "job_integration_1")
        assert rq_job.get_status() in ("queued", "deferred")

        worker = SimpleWorker([queue], connection=redis_connection)
        worked = worker.work(burst=True)

        assert worked is True
        rq_job.refresh()
        assert rq_job.get_status() == "finished"
        mock_running.assert_called_once()
        mock_completed.assert_called_once()
        mock_save.assert_called_once()
