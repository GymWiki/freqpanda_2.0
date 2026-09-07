"""Storage layer: upsert candles into Postgres/Supabase and read them back
out as the pandas DataFrame format the phase-1 interpreter expects.

Uses a direct Postgres connection (via `psycopg2`) rather than Supabase's
REST/PostgREST client. Supabase exposes both; for this phase the workload is
bulk time-series upserts and ranged reads, where raw SQL with
`execute_values` + `ON CONFLICT` is both simpler to reason about and far
more efficient than doing per-row REST calls. See the README for more on
this choice.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Optional, Sequence

import pandas as pd
import psycopg2
import psycopg2.extras

from .exchange import Candle

DATABASE_URL_ENV_VARS = ("SUPABASE_DB_URL", "DATABASE_URL")

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")

_UPSERT_SQL = """
insert into ohlcv_candles (exchange, symbol, timeframe, timestamp, open, high, low, close, volume)
values %s
on conflict (exchange, symbol, timeframe, timestamp)
do update set
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    volume = excluded.volume
"""

_LATEST_TIMESTAMP_SQL = """
select max(timestamp) from ohlcv_candles
where exchange = %s and symbol = %s and timeframe = %s
"""

_SELECT_SQL_TEMPLATE = """
select timestamp, open, high, low, close, volume from ohlcv_candles
where exchange = %s and symbol = %s and timeframe = %s{range_clause}
order by timestamp asc
"""


def get_connection(database_url: Optional[str] = None):
    url = database_url
    if url is None:
        for env_var in DATABASE_URL_ENV_VARS:
            url = os.environ.get(env_var)
            if url:
                break
    if not url:
        raise RuntimeError(
            "No database URL provided and none of "
            f"{DATABASE_URL_ENV_VARS} is set"
        )
    return psycopg2.connect(url)


def _candle_timestamp(ms: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)


def upsert_candles(
    conn, exchange: str, symbol: str, timeframe: str, candles: Sequence[Candle]
) -> int:
    """Insert `candles` (raw CCXT rows), overwriting any existing rows for
    the same (exchange, symbol, timeframe, timestamp). Returns the number of
    rows written. A no-op (returns 0) when `candles` is empty.
    """
    if not candles:
        return 0
    rows = [
        (exchange, symbol, timeframe, _candle_timestamp(c[0]), c[1], c[2], c[3], c[4], c[5])
        for c in candles
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, _UPSERT_SQL, rows)
    conn.commit()
    return len(rows)


def get_latest_timestamp_ms(conn, exchange: str, symbol: str, timeframe: str) -> Optional[int]:
    """The ms epoch timestamp of the most recently stored candle for this
    (exchange, symbol, timeframe), or None if nothing is stored yet.
    """
    with conn.cursor() as cur:
        cur.execute(_LATEST_TIMESTAMP_SQL, (exchange, symbol, timeframe))
        (latest,) = cur.fetchone()
    if latest is None:
        return None
    return int(latest.timestamp() * 1000)


def fetch_ohlcv_dataframe(
    conn,
    exchange: str,
    symbol: str,
    timeframe: str,
    start: Optional[dt.datetime] = None,
    end: Optional[dt.datetime] = None,
) -> pd.DataFrame:
    """Read stored candles back as the exact DataFrame shape the phase-1
    interpreter (`freqpanda_strategy.run_strategy`) expects: a DatetimeIndex
    sorted ascending, with float `open`/`high`/`low`/`close`/`volume`
    columns and nothing else.
    """
    params = [exchange, symbol, timeframe]
    range_clause = ""
    if start is not None:
        range_clause += " and timestamp >= %s"
        params.append(start)
    if end is not None:
        range_clause += " and timestamp <= %s"
        params.append(end)
    query = _SELECT_SQL_TEMPLATE.format(range_clause=range_clause)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=["timestamp", *OHLCV_COLUMNS])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df.index.name = None
    return df[list(OHLCV_COLUMNS)].astype(float)
