from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..auth import require_api_key
from ..db import get_db
from ..repositories import jobs as jobs_repo
from ..repositories import results as results_repo
from ..repositories import strategies as strategies_repo

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=List[schemas.CompareRow])
def compare_backtests(
    request: schemas.CompareRequest, created_by: str = Depends(require_api_key), conn=Depends(get_db)
):
    """Side-by-side metrics for a set of completed backtest jobs -- across
    different strategies, or the same strategy at different times/params.
    """
    rows = []
    for job_id in request.job_ids:
        job = jobs_repo.get_job(conn, job_id, created_by)
        if job is None or job.job_type != "backtest":
            raise HTTPException(status_code=404, detail=f"Backtest job '{job_id}' not found")
        if job.status != "completed":
            raise HTTPException(
                status_code=409, detail=f"Backtest job '{job_id}' is not completed yet (status={job.status})"
            )
        result = results_repo.get_backtest_result(conn, job_id)
        strategy = strategies_repo.get_strategy(conn, job.strategy_id, created_by)
        rows.append(
            schemas.CompareRow(
                job_id=job_id,
                strategy_id=job.strategy_id,
                strategy_name=strategy.name if strategy else "(deleted)",
                metrics=result["metrics"],
            )
        )
    return rows
