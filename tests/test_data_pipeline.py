from unittest.mock import MagicMock, patch

from freqpanda_data.config import PipelineConfig, SymbolTimeframe
from freqpanda_data.pipeline import run_pipeline, update_symbol_timeframe

HOUR_MS = 3_600_000


def _fake_exchange(now_ms):
    exchange = MagicMock()
    exchange.parse_timeframe.return_value = 3600
    exchange.milliseconds.return_value = now_ms
    return exchange


def test_update_symbol_timeframe_uses_backfill_since_when_nothing_stored():
    exchange = _fake_exchange(now_ms=10 * HOUR_MS)
    conn = MagicMock()

    with patch("freqpanda_data.pipeline.get_latest_timestamp_ms", return_value=None) as get_latest, \
         patch("freqpanda_data.pipeline.fetch_ohlcv_since", return_value=iter([])) as fetch_since:
        update_symbol_timeframe(conn, exchange, "binance", "BTC/USDT", "1h", default_since_ms=0)

    get_latest.assert_called_once_with(conn, "binance", "BTC/USDT", "1h")
    fetch_since.assert_called_once_with(exchange, "BTC/USDT", "1h", 0)


def test_update_symbol_timeframe_resumes_after_latest_stored_candle():
    exchange = _fake_exchange(now_ms=10 * HOUR_MS)
    conn = MagicMock()
    latest_stored_ms = 3 * HOUR_MS

    with patch("freqpanda_data.pipeline.get_latest_timestamp_ms", return_value=latest_stored_ms), \
         patch("freqpanda_data.pipeline.fetch_ohlcv_since", return_value=iter([])) as fetch_since:
        update_symbol_timeframe(conn, exchange, "binance", "BTC/USDT", "1h", default_since_ms=0)

    # Should resume one timeframe *after* the latest stored candle, not
    # re-fetch it.
    fetch_since.assert_called_once_with(exchange, "BTC/USDT", "1h", latest_stored_ms + HOUR_MS)


def test_update_symbol_timeframe_skips_fetch_when_already_up_to_date():
    exchange = _fake_exchange(now_ms=5 * HOUR_MS)
    conn = MagicMock()

    with patch("freqpanda_data.pipeline.get_latest_timestamp_ms", return_value=5 * HOUR_MS), \
         patch("freqpanda_data.pipeline.fetch_ohlcv_since") as fetch_since, \
         patch("freqpanda_data.pipeline.upsert_candles") as upsert:
        written = update_symbol_timeframe(conn, exchange, "binance", "BTC/USDT", "1h", default_since_ms=0)

    assert written == 0
    fetch_since.assert_not_called()
    upsert.assert_not_called()


def test_update_symbol_timeframe_filters_out_forming_candle_and_stores_rest():
    now_ms = 5 * HOUR_MS
    exchange = _fake_exchange(now_ms=now_ms)
    conn = MagicMock()
    closed_candle = [3 * HOUR_MS, 1, 2, 0.5, 1.5, 10]
    forming_candle = [4 * HOUR_MS, 1, 2, 0.5, 1.5, 10]  # closes at 5h == now, still counts as closed
    still_open_candle = [now_ms, 1, 2, 0.5, 1.5, 10]  # closes at 6h, in the future

    with patch("freqpanda_data.pipeline.get_latest_timestamp_ms", return_value=None), \
         patch(
             "freqpanda_data.pipeline.fetch_ohlcv_since",
             return_value=iter([[closed_candle, forming_candle, still_open_candle]]),
         ), \
         patch("freqpanda_data.pipeline.upsert_candles", return_value=2) as upsert:
        written = update_symbol_timeframe(conn, exchange, "binance", "BTC/USDT", "1h", default_since_ms=0)

    assert written == 2
    upsert.assert_called_once_with(conn, "binance", "BTC/USDT", "1h", [closed_candle, forming_candle])


def test_run_pipeline_updates_every_configured_pair_and_isolates_failures():
    config = PipelineConfig(
        exchange_id="binance",
        pairs=[
            SymbolTimeframe(symbol="BTC/USDT", timeframe="1h"),
            SymbolTimeframe(symbol="ETH/USDT", timeframe="4h"),
        ],
        backfill_since="2020-01-01T00:00:00Z",
    )

    fake_conn = MagicMock()
    fake_exchange = MagicMock()
    fake_exchange.parse8601.return_value = 0

    def fake_update(conn, exchange, exchange_id, symbol, timeframe, default_since_ms):
        if symbol == "ETH/USDT":
            raise RuntimeError("exchange exploded")
        return 42

    with patch("freqpanda_data.pipeline.create_exchange", return_value=fake_exchange), \
         patch("freqpanda_data.pipeline.get_connection", return_value=fake_conn), \
         patch("freqpanda_data.pipeline.update_symbol_timeframe", side_effect=fake_update):
        results = run_pipeline(config)

    assert results == {"BTC/USDT:1h": 42, "ETH/USDT:4h": None}
    fake_conn.close.assert_called_once()
