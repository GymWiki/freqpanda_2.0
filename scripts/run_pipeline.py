#!/usr/bin/env python
"""Run the data pipeline once for every symbol/timeframe in a config file.

Usage:
    export SUPABASE_DB_URL="postgresql://postgres:...@....supabase.co:5432/postgres"
    python scripts/run_pipeline.py config/pipeline.json

Intended to be invoked by cron (or, later, a job-queue worker in phase 5)
for periodic incremental updates -- each run only fetches candles newer
than what's already stored, so running it every few minutes is cheap.
"""
from __future__ import annotations

import logging
import sys

from freqpanda_data import load_pipeline_config, run_pipeline


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-pipeline-config.json>", file=sys.stderr)
        raise SystemExit(1)

    config = load_pipeline_config(sys.argv[1])
    results = run_pipeline(config)

    failed = [key for key, written in results.items() if written is None]
    if failed:
        raise SystemExit(f"Failed to update: {', '.join(failed)}")


if __name__ == "__main__":
    main()
