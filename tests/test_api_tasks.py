"""Unit tests for the worker functions in freqpanda_api.jobs.tasks: mock
the DB/repository layer and the OHLCV read, but run the real
freqpanda_backtest/freqpanda_optimize code against real synthetic data, so
these actually exercise the job-lifecycle logic (mark_running -> compute ->
save -> mark_completed, or mark_failed on error).
"""
from unittest.mock import MagicMock, patch

import pytest

from freqpanda_api.jobs.tasks import run_backtest_job, run_optimization_job
from freqpanda_api.repositories.jobs import JobRecord
from freqpanda_api.repositories.strategies import StrategyRecord
from freqpanda_strategy import IndicatorConfig, ParamRange, RiskManagement, StrategyDefinition

from conftest import generate_synthetic_ohlcv


def _ema_definition():
    return StrategyDefinition(
        name="ema_test",
        indicators=[
            IndicatorConfig(name="ema", alias="ema_fast", params={"period": 5}),
            IndicatorConfig(name="ema", alias="ema_slow", params={"period": 20}),
        ],
        entry_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_above", "right": "ema_slow"},
        exit_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_below", "right": "ema_slow"},
        risk_management=RiskManagement(stop_loss_pct=0.03, take_profit_pct=0.08),
    )


def _tunable_ema_definition():
    return StrategyDefinition(
        name="ema_tunable",
        indicators=[
            IndicatorConfig(
                name="ema", alias="ema_fast", params={"period": ParamRange(default=5, min=5, max=10, step=1)}
            ),
            IndicatorConfig(
                name="ema", alias="ema_slow", params={"period": ParamRange(default=20, min=20, max=30, step=1)}
            ),
        ],
        entry_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_above", "right": "ema_slow"},
        exit_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_below", "right": "ema_slow"},
        risk_management=RiskManagement(stop_loss_pct=0.03, take_profit_pct=0.08),
    )


def _job_record(job_type="backtest", payload=None):
    return JobRecord(
        id="job_1",
        job_type=job_type,
        status="pending",
        strategy_id="strat_1",
        payload=payload or {"exchange": "binance", "symbol": "BTC/USDT", "timeframe": "1h"},
        error=None,
        created_by="owner-hash",
        created_at=None,
        started_at=None,
        finished_at=None,
    )


def _strategy_record(definition):
    return StrategyRecord(
        id="strat_1", name=definition.name, definition=definition, created_by="owner-hash",
        created_at=None, updated_at=None,
    )


@patch("freqpanda_api.jobs.tasks.get_data_connection", return_value=MagicMock())
@patch("freqpanda_api.jobs.tasks.results_repo.save_backtest_result")
@patch("freqpanda_api.jobs.tasks.jobs_repo.mark_completed")
@patch("freqpanda_api.jobs.tasks.jobs_repo.mark_running")
@patch("freqpanda_api.jobs.tasks.jobs_repo.mark_failed")
@patch("freqpanda_api.jobs.tasks.strategies_repo.get_strategy")
@patch("freqpanda_api.jobs.tasks.jobs_repo.get_job_unscoped")
@patch("freqpanda_api.jobs.tasks.fetch_ohlcv_dataframe")
def test_run_backtest_job_happy_path(
    mock_fetch, mock_get_job, mock_get_strategy, mock_mark_failed, mock_mark_running,
    mock_mark_completed, mock_save, mock_get_conn,
):
    definition = _ema_definition()
    mock_get_job.return_value = _job_record()
    mock_get_strategy.return_value = _strategy_record(definition)
    mock_fetch.return_value = generate_synthetic_ohlcv(n=500)

    run_backtest_job("job_1")

    mock_mark_running.assert_called_once_with(mock_get_conn.return_value, "job_1")
    mock_save.assert_called_once()
    saved_job_id, saved_strategy_id, saved_result = mock_save.call_args[0][1:]
    assert saved_job_id == "job_1"
    assert saved_strategy_id == "strat_1"
    assert saved_result.strategy_name == "ema_test"
    mock_mark_completed.assert_called_once()
    mock_mark_failed.assert_not_called()


@patch("freqpanda_api.jobs.tasks.get_data_connection", return_value=MagicMock())
@patch("freqpanda_api.jobs.tasks.jobs_repo.mark_failed")
@patch("freqpanda_api.jobs.tasks.jobs_repo.mark_running")
@patch("freqpanda_api.jobs.tasks.strategies_repo.get_strategy")
@patch("freqpanda_api.jobs.tasks.jobs_repo.get_job_unscoped")
@patch("freqpanda_api.jobs.tasks.fetch_ohlcv_dataframe")
def test_run_backtest_job_marks_failed_when_no_data(
    mock_fetch, mock_get_job, mock_get_strategy, mock_mark_running, mock_mark_failed, mock_get_conn,
):
    import pandas as pd

    mock_get_job.return_value = _job_record()
    mock_get_strategy.return_value = _strategy_record(_ema_definition())
    mock_fetch.return_value = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    with pytest.raises(RuntimeError, match="No stored OHLCV data"):
        run_backtest_job("job_1")

    mock_mark_failed.assert_called_once()
    error_message = mock_mark_failed.call_args[0][2]
    assert "No stored OHLCV data" in error_message
    # The connection must be rolled back before mark_failed writes to it --
    # otherwise, if the exception path itself involved a failed statement,
    # this UPDATE would raise InFailedSqlTransaction and the job would be
    # left stuck on "running" forever.
    mock_get_conn.return_value.rollback.assert_called_once()


@patch("freqpanda_api.jobs.tasks.get_data_connection", return_value=MagicMock())
@patch("freqpanda_api.jobs.tasks.jobs_repo.get_job_unscoped", return_value=None)
def test_run_backtest_job_noop_when_job_missing(mock_get_job, mock_get_conn):
    run_backtest_job("does_not_exist")  # should not raise


@patch("freqpanda_api.jobs.tasks.get_data_connection", return_value=MagicMock())
@patch("freqpanda_api.jobs.tasks.results_repo.save_optimization_result")
@patch("freqpanda_api.jobs.tasks.jobs_repo.mark_completed")
@patch("freqpanda_api.jobs.tasks.jobs_repo.mark_running")
@patch("freqpanda_api.jobs.tasks.jobs_repo.mark_failed")
@patch("freqpanda_api.jobs.tasks.strategies_repo.get_strategy")
@patch("freqpanda_api.jobs.tasks.jobs_repo.get_job_unscoped")
@patch("freqpanda_api.jobs.tasks.fetch_ohlcv_dataframe")
def test_run_optimization_job_happy_path(
    mock_fetch, mock_get_job, mock_get_strategy, mock_mark_failed, mock_mark_running,
    mock_mark_completed, mock_save, mock_get_conn,
):
    definition = _tunable_ema_definition()
    payload = {
        "exchange": "binance", "symbol": "BTC/USDT", "timeframe": "1h",
        "train_period_days": 10, "test_period_days": 3, "n_trials": 2, "metric": "sharpe_ratio",
    }
    mock_get_job.return_value = _job_record(job_type="optimization", payload=payload)
    mock_get_strategy.return_value = _strategy_record(definition)
    mock_fetch.return_value = generate_synthetic_ohlcv(n=500)

    run_optimization_job("job_1")

    mock_mark_completed.assert_called_once()
    mock_mark_failed.assert_not_called()
    mock_save.assert_called_once()
    args = mock_save.call_args[0]
    assert args[1] == "job_1"
    assert args[2] == "strat_1"
    assert args[3] == "sharpe_ratio"
    windows = args[4]
    assert isinstance(windows, list) and len(windows) > 0
    assert "best_params" in windows[0]
