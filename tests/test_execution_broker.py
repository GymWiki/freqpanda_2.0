from unittest.mock import MagicMock

import pytest

from freqpanda_backtest.costs import TradingCosts
from freqpanda_execution.broker import LiveBroker, PaperBroker


# ---- PaperBroker ----


def test_paper_broker_open_long_applies_slippage_and_fee():
    broker = PaperBroker(TradingCosts(fee_pct=0.001, slippage_pct=0.002))
    fill = broker.open_long("BTC/USDT", equity=1000.0, fee_pct=0.001, reference_price=100.0)

    expected_price = 100.0 * 1.002
    expected_quantity = (1000.0 * (1 - 0.001)) / expected_price
    assert fill.price == pytest.approx(expected_price)
    assert fill.quantity == pytest.approx(expected_quantity)
    assert fill.order_id is None


def test_paper_broker_close_long_applies_negative_slippage():
    broker = PaperBroker(TradingCosts(fee_pct=0.001, slippage_pct=0.002))
    fill = broker.close_long("BTC/USDT", quantity=5.0, reference_price=100.0)

    assert fill.price == pytest.approx(100.0 * 0.998)
    assert fill.quantity == 5.0
    assert fill.order_id is None


def test_paper_broker_with_zero_costs_fills_at_reference_price():
    broker = PaperBroker(TradingCosts())
    entry = broker.open_long("BTC/USDT", equity=1000.0, fee_pct=0.0, reference_price=50.0)
    assert entry.price == pytest.approx(50.0)
    assert entry.quantity == pytest.approx(20.0)


# ---- LiveBroker ----


def test_live_broker_open_long_places_estimated_quantity_and_uses_reported_fill():
    exchange = MagicMock()
    exchange.create_market_buy_order.return_value = {"id": "abc123", "average": 101.5, "filled": 9.85}
    broker = LiveBroker(exchange)

    fill = broker.open_long("BTC/USDT", equity=1000.0, fee_pct=0.001, reference_price=100.0)

    expected_estimated_quantity = (1000.0 * 0.999) / 100.0
    exchange.create_market_buy_order.assert_called_once()
    args, _ = exchange.create_market_buy_order.call_args
    assert args[0] == "BTC/USDT"
    assert args[1] == pytest.approx(expected_estimated_quantity)

    assert fill.price == 101.5
    assert fill.quantity == 9.85
    assert fill.order_id == "abc123"


def test_live_broker_close_long_uses_reported_average_price():
    exchange = MagicMock()
    exchange.create_market_sell_order.return_value = {"id": "xyz", "average": 98.0, "filled": 5.0}
    broker = LiveBroker(exchange)

    fill = broker.close_long("BTC/USDT", quantity=5.0, reference_price=100.0)

    exchange.create_market_sell_order.assert_called_once_with("BTC/USDT", 5.0)
    assert fill.price == 98.0
    assert fill.quantity == 5.0
    assert fill.order_id == "xyz"


def test_live_broker_falls_back_to_price_field_when_average_is_missing():
    exchange = MagicMock()
    exchange.create_market_buy_order.return_value = {"id": "abc", "average": None, "price": 99.9, "filled": None}
    broker = LiveBroker(exchange)

    fill = broker.open_long("BTC/USDT", equity=1000.0, fee_pct=0.0, reference_price=100.0)

    assert fill.price == 99.9
    assert fill.quantity == pytest.approx(10.0)  # falls back to the requested/estimated quantity


def test_live_broker_raises_when_exchange_reports_no_fill_price():
    exchange = MagicMock()
    exchange.create_market_buy_order.return_value = {"id": "abc", "average": None, "price": None}
    broker = LiveBroker(exchange)

    with pytest.raises(RuntimeError, match="did not report a fill price"):
        broker.open_long("BTC/USDT", equity=1000.0, fee_pct=0.0, reference_price=100.0)


def test_live_broker_get_quote_balance_reads_free_balance():
    exchange = MagicMock()
    exchange.fetch_balance.return_value = {"USDT": {"free": 250.5, "total": 300.0}}
    broker = LiveBroker(exchange)

    assert broker.get_quote_balance("USDT") == 250.5


def test_live_broker_get_quote_balance_defaults_to_zero_for_unknown_currency():
    exchange = MagicMock()
    exchange.fetch_balance.return_value = {}
    broker = LiveBroker(exchange)

    assert broker.get_quote_balance("EUR") == 0.0
