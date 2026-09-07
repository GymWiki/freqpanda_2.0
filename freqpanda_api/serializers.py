"""Small shared mappers from repository dataclasses to API response models,
to avoid repeating the same field list in every router.
"""
from __future__ import annotations

from . import schemas
from .repositories.jobs import JobRecord
from .repositories.strategies import StrategyRecord


def strategy_to_response(record: StrategyRecord) -> schemas.StrategyResponse:
    return schemas.StrategyResponse(
        id=record.id,
        name=record.name,
        definition=record.definition,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def job_to_response(job: JobRecord) -> schemas.JobResponse:
    return schemas.JobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        strategy_id=job.strategy_id,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
