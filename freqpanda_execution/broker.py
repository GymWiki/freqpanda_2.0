"""Where a trading decision turns into an actual fill -- simulated for
paper mode, real for live mode. Both implement the same `Broker` interface
so `freqpanda_execution.bot` never branches on which mode it's running in.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import ccxt

from freqpanda_backtest.costs import TradingCosts


@dataclass(frozen=True)
class Fill:
    price: float
    quantity: float
    order_id: Optional[str]  # None for paper fills; the exchange order id for live


class Broker(ABC):
    @abstractmethod
    def open_long(self, symbol: str, equity: float, fee_pct: float, reference_price: float) -> Fill:
        """Deploy `equity` (quote currency) into a long position at
        (approximately) `reference_price`; return the fill actually
        realized.
        """

    @abstractmethod
    def close_long(self, symbol: str, quantity: float, reference_price: float) -> Fill:
        """Sell `quantity` of the base asset; return the fill actually
        realized.
        """


class PaperBroker(Broker):
    """Fills instantly at `reference_price`, adjusted for fee/slippage via
    the exact same `TradingCosts` model phase 3 uses for backtests -- so a
    paper bot's fills are computed identically to a backtest's, just
    against real-time prices instead of historical ones. No exchange call,
    no order id.
    """

    def __init__(self, costs: TradingCosts):
        self.costs = costs

    def open_long(self, symbol: str, equity: float, fee_pct: float, reference_price: float) -> Fill:
        fill_price = self.costs.entry_fill_price(reference_price)
        quantity = (equity * (1 - self.costs.fee_pct)) / fill_price
        return Fill(price=fill_price, quantity=quantity, order_id=None)

    def close_long(self, symbol: str, quantity: float, reference_price: float) -> Fill:
        fill_price = self.costs.exit_fill_price(reference_price)
        return Fill(price=fill_price, quantity=quantity, order_id=None)


class LiveBroker(Broker):
    """Places real market orders through a CCXT exchange instance.

    `quantity` sent to the exchange is *estimated* from `reference_price`
    (the latest closed candle) since the real fill price isn't known until
    the order executes; the fill returned uses the exchange's own reported
    average price, which becomes the real entry/exit price the rest of the
    system tracks from then on -- never the estimate.
    """

    def __init__(self, exchange: ccxt.Exchange):
        self.exchange = exchange

    def open_long(self, symbol: str, equity: float, fee_pct: float, reference_price: float) -> Fill:
        estimated_quantity = (equity * (1 - fee_pct)) / reference_price
        order = self.exchange.create_market_buy_order(symbol, estimated_quantity)
        return self._fill_from_order(order, estimated_quantity)

    def close_long(self, symbol: str, quantity: float, reference_price: float) -> Fill:
        order = self.exchange.create_market_sell_order(symbol, quantity)
        return self._fill_from_order(order, quantity)

    def get_quote_balance(self, currency: str) -> float:
        balance = self.exchange.fetch_balance()
        return float(balance.get(currency, {}).get("free", 0.0))

    @staticmethod
    def _fill_from_order(order: dict, requested_quantity: float) -> Fill:
        price = order.get("average") or order.get("price")
        if price is None:
            raise RuntimeError(f"Exchange did not report a fill price for order {order.get('id')!r}: {order}")
        filled = order.get("filled") or requested_quantity
        return Fill(price=float(price), quantity=float(filled), order_id=str(order.get("id")))
