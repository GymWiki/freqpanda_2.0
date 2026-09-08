"""Process entrypoint for exactly one bot.

Usage: `python -m freqpanda_execution.runner <bot_id>`

Every bot runs as its own OS process (spawned by `supervisor.py`, or
directly for local development/debugging) so that one bot's crash --
an unhandled exchange error, a bug -- can never take another bot down
with it; the only thing two bots ever share is the Postgres database.

SIGTERM/SIGINT trigger a graceful shutdown: the running `Bot.stop()` is
called, which lets the current `feed.run()` iteration finish (state is
saved after every candle close, see `bot.py`) rather than killing the
process mid-write.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

from freqpanda_data.db import get_connection

from .bot import build_bot
from .config import get_settings

logger = logging.getLogger(__name__)


async def _run(bot_id: str) -> None:
    settings = get_settings()
    conn = get_connection(settings.database_url)
    try:
        bot = build_bot(conn, bot_id)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, bot.stop)

        await bot.run()
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if len(argv) != 2:
        print("usage: python -m freqpanda_execution.runner <bot_id>", file=sys.stderr)
        return 2
    bot_id = argv[1]

    try:
        asyncio.run(_run(bot_id))
    except Exception:  # noqa: BLE001 -- last resort: log full traceback, exit non-zero so the supervisor sees a crash
        logger.exception("bot %s: runner exiting after unhandled error", bot_id)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
