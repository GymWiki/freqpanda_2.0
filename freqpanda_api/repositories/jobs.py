"""Job bookkeeping: one row per backtest/optimization job, tracking status
through pending -> running -> completed/failed. The job queue itself (RQ)
only needs to know a job id and which function to call; all state a client
might poll for lives here, not in Redis, so job history survives a Redis
restart and stays queryable with plain SQL.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Literal, Optional

from psycopg2.extras import Json

from ..ids import new_id

JobType = Literal["backtest", "optimization"]
JobStatus = Literal["pending", "running", "completed", "failed"]

_COLUMNS = "id, job_type, status, strategy_id, payload, error, created_by, created_at, started_at, finished_at"


@dataclass(frozen=True)
class JobRecord:
    id: str
    job_type: JobType
    status: JobStatus
    strategy_id: str
    payload: dict
    error: Optional[str]
    created_by: str
    created_at: dt.datetime
    started_at: Optional[dt.datetime]
    finished_at: Optional[dt.datetime]


def _row_to_record(row) -> JobRecord:
    id_, job_type, status, strategy_id, payload, error, created_by, created_at, started_at, finished_at = row
    return JobRecord(
        id=id_,
        job_type=job_type,
        status=status,
        strategy_id=strategy_id,
        payload=payload,
        error=error,
        created_by=created_by,
        created_at=created_at,
        started_at=started_at,
        finished_at=finished_at,
    )


def create_job(conn, job_type: JobType, strategy_id: str, payload: dict, created_by: str) -> JobRecord:
    job_id = new_id("job")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            insert into jobs (id, job_type, strategy_id, payload, created_by)
            values (%s, %s, %s, %s, %s)
            returning {_COLUMNS}
            """,
            (job_id, job_type, strategy_id, Json(payload), created_by),
        )
        row = cur.fetchone()
    conn.commit()
    return _row_to_record(row)


def get_job(conn, job_id: str, created_by: str) -> Optional[JobRecord]:
    with conn.cursor() as cur:
        cur.execute(f"select {_COLUMNS} from jobs where id = %s and created_by = %s", (job_id, created_by))
        row = cur.fetchone()
    return _row_to_record(row) if row else None


def get_job_unscoped(conn, job_id: str) -> Optional[JobRecord]:
    """Used by the worker, which has no notion of "the calling API key" --
    it's told a job id and looks up whatever's there.
    """
    with conn.cursor() as cur:
        cur.execute(f"select {_COLUMNS} from jobs where id = %s", (job_id,))
        row = cur.fetchone()
    return _row_to_record(row) if row else None


def list_jobs(conn, strategy_id: str, job_type: JobType, created_by: str) -> List[JobRecord]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            select {_COLUMNS} from jobs
            where strategy_id = %s and job_type = %s and created_by = %s
            order by created_at desc
            """,
            (strategy_id, job_type, created_by),
        )
        rows = cur.fetchall()
    return [_row_to_record(row) for row in rows]


def mark_running(conn, job_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("update jobs set status = 'running', started_at = now() where id = %s", (job_id,))
    conn.commit()


def mark_completed(conn, job_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("update jobs set status = 'completed', finished_at = now() where id = %s", (job_id,))
    conn.commit()


def mark_failed(conn, job_id: str, error: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "update jobs set status = 'failed', error = %s, finished_at = now() where id = %s",
            (error, job_id),
        )
    conn.commit()
