from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from .. import schemas
from ..auth import require_api_key
from ..db import get_db
from ..jobs.queue import get_queue
from ..jobs.tasks import run_backtest_job
from ..repositories import jobs as jobs_repo
from ..repositories import results as results_repo
from ..repositories import strategies as strategies_repo
from ..serializers import job_to_response

router = APIRouter(tags=["backtests"])


@router.post(
    "/strategies/{strategy_id}/backtests",
    response_model=schemas.JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_backtest(
    strategy_id: str,
    request: schemas.BacktestJobRequest,
    created_by: str = Depends(require_api_key),
    conn=Depends(get_db),
):
    """Enqueues a backtest job and returns immediately with its id/status
    (`pending`) -- poll `GET /backtests/{job_id}` for the result. The job
    reads OHLCV from phase 2's storage; if that symbol/timeframe hasn't
    been backfilled yet, the job fails with a clear error rather than the
    request blocking on a live exchange fetch.
    """
    strategy = strategies_repo.get_strategy(conn, strategy_id, created_by)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    payload = request.model_dump(mode="json")
    job = jobs_repo.create_job(conn, "backtest", strategy.id, payload, created_by)
    get_queue().enqueue(run_backtest_job, job.id, job_id=job.id)
    return job_to_response(job)


@router.get("/strategies/{strategy_id}/backtests", response_model=List[schemas.BacktestSummary])
def list_backtests(strategy_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    strategy = strategies_repo.get_strategy(conn, strategy_id, created_by)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return results_repo.list_backtest_summaries(conn, strategy_id, created_by)


@router.get("/backtests/{job_id}", response_model=schemas.BacktestDetailResponse)
def get_backtest(job_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    job = jobs_repo.get_job(conn, job_id, created_by)
    if job is None or job.job_type != "backtest":
        raise HTTPException(status_code=404, detail="Backtest job not found")

    result = results_repo.get_backtest_result(conn, job_id) or {}
    base = job_to_response(job)
    return schemas.BacktestDetailResponse(
        **base.model_dump(),
        metrics=result.get("metrics"),
        trades=result.get("trades"),
        equity_curve=result.get("equity_curve"),
    )
