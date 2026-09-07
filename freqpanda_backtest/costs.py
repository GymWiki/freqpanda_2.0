"""Trading cost model: fees and slippage applied per fill (entry and exit).

Kept as a tiny standalone value object so `equity.py` and `backtest.py`
share one definition of "what does a fill actually cost", instead of the
fee/slippage math being duplicated wherever a price is turned into an
executed price.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradingCosts:
    """Fractions, e.g. `fee_pct=0.001` == 0.1% taker fee per fill.

    `slippage_pct` models adverse price movement between deciding to trade
    and the fill: paying more than the raw price to buy, receiving less than
    the raw price to sell. Both default in a way that keeps a bare
    `backtest()` call runnable, but a fee of 0 is unrealistic for real
    exchanges -- see the README for suggested defaults.
    """

    fee_pct: float = 0.0
    slippage_pct: float = 0.0

    def entry_fill_price(self, raw_price: float) -> float:
        return raw_price * (1 + self.slippage_pct)

    def exit_fill_price(self, raw_price: float) -> float:
        return raw_price * (1 - self.slippage_pct)
