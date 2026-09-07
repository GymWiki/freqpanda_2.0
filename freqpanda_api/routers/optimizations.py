from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from .. import schemas
from ..auth import require_api_key
from ..db import get_db
from ..jobs.queue import get_queue
from ..jobs.tasks import run_optimization_job
from ..repositories import jobs as jobs_repo
from ..repositories import results as results_repo
from ..repositories import strategies as strategies_repo
from ..serializers import job_to_response

router = APIRouter(tags=["optimizations"])


@router.post(
    "/strategies/{strategy_id}/optimizations",
    response_model=schemas.JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_optimization(
    strategy_id: str,
    request: schemas.OptimizationJobRequest,
    created_by: str = Depends(require_api_key),
    conn=Depends(get_db),
):
    """Enqueues a walk-forward optimization job (phase 4's `optimize()` +
    `refit_on_full_history()`) -- same async pattern as backtests: returns
    a job id immediately, poll `GET /optimizations/{job_id}`.
    """
    strategy = strategies_repo.get_strategy(conn, strategy_id, created_by)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    payload = request.model_dump(mode="json")
    job = jobs_repo.create_job(conn, "optimization", strategy.id, payload, created_by)
    get_queue().enqueue(run_optimization_job, job.id, job_id=job.id)
    return job_to_response(job)


@router.get("/strategies/{strategy_id}/optimizations", response_model=List[schemas.OptimizationSummary])
def list_optimizations(strategy_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    strategy = strategies_repo.get_strategy(conn, strategy_id, created_by)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return results_repo.list_optimization_summaries(conn, strategy_id, created_by)


@router.get("/optimizations/{job_id}", response_model=schemas.OptimizationDetailResponse)
def get_optimization(job_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    job = jobs_repo.get_job(conn, job_id, created_by)
    if job is None or job.job_type != "optimization":
        raise HTTPException(status_code=404, detail="Optimization job not found")

    result = results_repo.get_optimization_result(conn, job_id) or {}
    base = job_to_response(job)
    return schemas.OptimizationDetailResponse(
        **base.model_dump(),
        metric=result.get("metric"),
        windows=result.get("windows"),
        mean_in_sample_score=result.get("mean_in_sample_score"),
        mean_out_of_sample_score=result.get("mean_out_of_sample_score"),
        final_params=result.get("final_params"),
        final_definition=result.get("final_definition"),
    )
