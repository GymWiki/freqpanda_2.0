"""Confirms the phase-2 storage layer's DataFrame output is exactly what
the phase-1 interpreter expects -- the whole point of matching the format.
"""
from unittest.mock import MagicMock

from freqpanda_data.db import fetch_ohlcv_dataframe
from freqpanda_strategy import load_strategy_definition, run_strategy

from conftest import generate_synthetic_ohlcv


def test_stored_data_round_trips_through_the_phase1_interpreter():
    synthetic = generate_synthetic_ohlcv()
    rows = [
        (ts.to_pydatetime(), r.open, r.high, r.low, r.close, r.volume)
        for ts, r in synthetic.iterrows()
    ]

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchall.return_value = rows

    df = fetch_ohlcv_dataframe(conn, "binance", "BTC/USDT", "1h")

    definition = load_strategy_definition("examples/ema_crossover.json")
    trades = run_strategy(definition, df)

    assert len(trades) > 0
    for trade in trades:
        assert trade.entry_time < trade.exit_time
