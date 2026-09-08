"""Reconciliation loop: keeps actually-running bot processes in sync with
`bots.desired_status`, so starting/stopping a bot from the webapp (via the
API) is just flipping a database column -- this process does the rest.

Analogous to a Kubernetes controller: desired state lives in the database
(`bots.desired_status`), actual state is "is there a live subprocess for
this bot_id", and this loop's only job is to make actual match desired,
forever, without ever needing to know *why* desired state changed.

One `subprocess.Popen` child per bot (`python -m freqpanda_execution.runner
<bot_id>`) -- not asyncio tasks in this same process -- so a bot that
crashes, deadlocks, or leaks memory cannot affect any other bot, or this
supervisor itself. See README.md for why this was chosen over an RQ queue
(designed for one-shot jobs, not long-running processes) or per-bot
containers (too much operational overhead for a single-VPS MVP).
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set

from freqpanda_data.db import get_connection

from . import repository
from .config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class _Child:
    process: subprocess.Popen
    restart_times: List[float] = field(default_factory=list)


class Supervisor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._children: Dict[str, _Child] = {}
        # Bots that crash-looped and are being left alone until
        # desired_status cycles off and back on -- see _reap_dead_children.
        self._given_up: Set[str] = set()

    def run_forever(self) -> None:
        logger.info("supervisor starting, polling every %.1fs", self.settings.supervisor_poll_interval_seconds)
        while True:
            try:
                self.reconcile_once()
            except Exception:  # noqa: BLE001 -- a reconciliation-loop bug must never kill the supervisor itself
                logger.exception("reconciliation pass failed")
            time.sleep(self.settings.supervisor_poll_interval_seconds)

    def reconcile_once(self) -> None:
        conn = get_connection(self.settings.database_url)
        try:
            desired_running = {b.id for b in repository.list_bots_by_desired_status(conn, "running")}
        finally:
            conn.close()

        # A bot that crash-looped and was since stopped (desired_status no
        # longer 'running') gets a clean slate if it's started again later.
        self._given_up &= desired_running

        self._reap_dead_children(desired_running)

        for bot_id in desired_running:
            if bot_id not in self._children and bot_id not in self._given_up:
                self._start(bot_id)

        for bot_id in list(self._children):
            if bot_id not in desired_running:
                self._stop(bot_id)

    def _reap_dead_children(self, desired_running: Set[str]) -> None:
        for bot_id, child in list(self._children.items()):
            exit_code = child.process.poll()
            if exit_code is None:
                continue  # still running

            del self._children[bot_id]
            if bot_id not in desired_running:
                logger.info("bot %s: process exited (code %s), no longer desired -- not restarting", bot_id, exit_code)
                continue

            now = time.monotonic()
            child.restart_times = [t for t in child.restart_times if now - t < self.settings.crash_loop_window_seconds]
            if len(child.restart_times) >= self.settings.max_restarts_in_window:
                logger.error(
                    "bot %s: crashed %d times within %.0fs, giving up until desired_status is toggled off and on",
                    bot_id, len(child.restart_times), self.settings.crash_loop_window_seconds,
                )
                self._given_up.add(bot_id)
                self._mark_error(
                    bot_id,
                    f"Crash-looped ({len(child.restart_times)} restarts in "
                    f"{self.settings.crash_loop_window_seconds:.0f}s); stopped restarting.",
                )
                continue

            logger.warning("bot %s: process exited unexpectedly (code %s), restarting", bot_id, exit_code)
            child.restart_times.append(now)
            self._spawn(bot_id, restart_times=child.restart_times)

    def _mark_error(self, bot_id: str, message: str) -> None:
        conn = get_connection(self.settings.database_url)
        try:
            repository.update_status(conn, bot_id, "error", message)
        finally:
            conn.close()

    def _start(self, bot_id: str) -> None:
        logger.info("bot %s: starting", bot_id)
        self._spawn(bot_id, restart_times=[])

    def _spawn(self, bot_id: str, restart_times: List[float]) -> None:
        process = subprocess.Popen([sys.executable, "-m", "freqpanda_execution.runner", bot_id])
        self._children[bot_id] = _Child(process=process, restart_times=restart_times)

    def _stop(self, bot_id: str) -> None:
        child = self._children.pop(bot_id)
        logger.info("bot %s: no longer desired, stopping", bot_id)
        child.process.terminate()
        try:
            child.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("bot %s: did not stop within 30s, killing", bot_id)
            child.process.kill()
            child.process.wait()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Supervisor(get_settings()).run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
