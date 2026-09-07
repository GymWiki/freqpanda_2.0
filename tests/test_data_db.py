import datetime as dt
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from freqpanda_data.db import (
    fetch_ohlcv_dataframe,
    get_connection,
    get_latest_timestamp_ms,
    upsert_candles,
)


def _mock_conn_with_cursor():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


def test_upsert_candles_writes_rows_and_commits():
    conn, cursor = _mock_conn_with_cursor()
    candles = [
        [1_700_000_000_000, 100.0, 101.0, 99.0, 100.5, 10.0],
        [1_700_003_600_000, 100.5, 102.0, 100.0, 101.5, 12.0],
    ]

    with patch("freqpanda_data.db.psycopg2.extras.execute_values") as execute_values:
        written = upsert_candles(conn, "binance", "BTC/USDT", "1h", candles)

    assert written == 2
    execute_values.assert_called_once()
    _, args, _ = execute_values.mock_calls[0]
    passed_cursor, sql, rows = args
    assert passed_cursor is cursor
    assert "on conflict" in sql.lower()
    assert rows[0][:4] == ("binance", "BTC/USDT", "1h", dt.datetime.fromtimestamp(1_700_000_000_000 / 1000, tz=dt.timezone.utc))
    assert rows[0][4:] == (100.0, 101.0, 99.0, 100.5, 10.0)
    conn.commit.assert_called_once()


def test_upsert_candles_empty_list_is_noop():
    conn, cursor = _mock_conn_with_cursor()
    with patch("freqpanda_data.db.psycopg2.extras.execute_values") as execute_values:
        written = upsert_candles(conn, "binance", "BTC/USDT", "1h", [])
    assert written == 0
    execute_values.assert_not_called()
    conn.commit.assert_not_called()


def test_get_latest_timestamp_ms_returns_none_when_empty():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = (None,)
    result = get_latest_timestamp_ms(conn, "binance", "BTC/USDT", "1h")
    assert result is None
    args, _ = cursor.execute.call_args
    assert args[1] == ("binance", "BTC/USDT", "1h")


def test_get_latest_timestamp_ms_returns_ms_epoch():
    conn, cursor = _mock_conn_with_cursor()
    stored_time = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    cursor.fetchone.return_value = (stored_time,)
    result = get_latest_timestamp_ms(conn, "binance", "BTC/USDT", "1h")
    assert result == int(stored_time.timestamp() * 1000)


def test_fetch_ohlcv_dataframe_shape_matches_interpreter_expectations():
    conn, cursor = _mock_conn_with_cursor()
    rows = [
        (dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc), 100.0, 101.0, 99.0, 100.5, 10.0),
        (dt.datetime(2024, 1, 1, 1, tzinfo=dt.timezone.utc), 100.5, 102.0, 100.0, 101.5, 12.0),
    ]
    cursor.fetchall.return_value = rows

    df = fetch_ohlcv_dataframe(conn, "binance", "BTC/USDT", "1h")

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing
    assert df["close"].tolist() == [100.5, 101.5]
    assert df.dtypes.apply(lambda d: d == float).all()


def test_fetch_ohlcv_dataframe_empty_result():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchall.return_value = []
    df = fetch_ohlcv_dataframe(conn, "binance", "BTC/USDT", "1h")
    assert df.empty
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_fetch_ohlcv_dataframe_applies_start_end_range():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchall.return_value = []
    start = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(2024, 1, 2, tzinfo=dt.timezone.utc)

    fetch_ohlcv_dataframe(conn, "binance", "BTC/USDT", "1h", start=start, end=end)

    query, params = cursor.execute.call_args[0]
    assert "timestamp >= %s" in query
    assert "timestamp <= %s" in query
    assert params == ["binance", "BTC/USDT", "1h", start, end]


def test_get_connection_uses_explicit_url():
    with patch("freqpanda_data.db.psycopg2.connect") as connect:
        get_connection("postgresql://explicit")
    connect.assert_called_once_with("postgresql://explicit")


def test_get_connection_falls_back_to_env_var(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://from-env")
    with patch("freqpanda_data.db.psycopg2.connect") as connect:
        get_connection()
    connect.assert_called_once_with("postgresql://from-env")


def test_get_connection_raises_without_url(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        get_connection()
