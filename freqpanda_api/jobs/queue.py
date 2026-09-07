"""RQ (Redis Queue) setup: one Redis instance, one named queue, worker
processes started separately (`rq worker <queue name>` or the
`freqpanda-worker` docker-compose service). See the package README for why
RQ over Celery/a dedicated broker for a single-VPS deployment.
"""
from __future__ import annotations

import redis
from rq import Queue

from ..config import get_settings


def get_redis_connection() -> redis.Redis:
    return redis.from_url(get_settings().redis_url)


def get_queue() -> Queue:
    settings = get_settings()
    return Queue(
        settings.job_queue_name,
        connection=get_redis_connection(),
        default_timeout=settings.job_timeout_seconds,
    )
