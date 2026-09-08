"""Risk middleware: three independent safety nets that sit between the
strategy's own decisions and the exchange, and that never depend on the
interpreter having decided correctly.

1. **Hard stop-loss** (`check_hard_stop_loss`) -- re-derives the strategy's
   own stop-loss level from `risk_management.stop_loss_pct` and checks it
   against every price update the feed sees, not just once per candle
   close. The interpreter (`freqpanda_strategy.run_strategy`) already
   enforces the same stop-loss, but only when it evaluates a closed candle;
   this is a second, independent check at tick granularity, so a slow
   candle (an illiquid pair, a long timeframe) or a bug in the live
   position-tracking loop (`freqpanda_execution.bot`) can't leave a
   position running past its stop past the point the strategy itself
   would have closed it.
2. **Max-drawdown circuit breaker** (`update_equity`) -- halts the bot
   entirely (raises `CircuitBreakerTripped`) once equity has fallen more
   than `max_drawdown_pct` from its peak. Unlike the stop-loss, this isn't
   about one trade -- it's "something about this strategy/market is wrong,
   stop trading and let a human look," independent of *why* the drawdown
   happened.
3. **Order sanity checks** (`check_order`) -- rejects an order before it
   reaches the exchange if its notional is disproportionate to account
   equity, its price is absurdly far from the last known market price, or
   its quantity/price aren't positive. This is the last line of defense
   against a bug (a bad fill-price calculation, a unit mixup) turning into
   a real order.

All three raise a specific exception rather than returning a bool, so a
caller can't accidentally ignore a tripped check by forgetting to look at a
return value.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class RiskViolation(Exception):
    """Base class for every risk-middleware rejection."""


class CircuitBreakerTripped(RiskViolation):
    pass


class OrderRejected(RiskViolation):
    pass


@dataclass(frozen=True)
class RiskLimits:
    max_drawdown_pct: float
    max_position_notional_pct: float = 1.0
    max_price_deviation_pct: float = 0.10
    min_seconds_between_orders: float = 1.0

    def __post_init__(self):
        if not (0 < self.max_drawdown_pct < 1):
            raise ValueError("max_drawdown_pct must be between 0 and 1")
        if self.max_position_notional_pct <= 0:
            raise ValueError("max_position_notional_pct must be positive")
        if self.max_price_deviation_pct <= 0:
            raise ValueError("max_price_deviation_pct must be positive")
        if self.min_seconds_between_orders < 0:
            raise ValueError("min_seconds_between_orders must not be negative")


class RiskMiddleware:
    def __init__(self, limits: RiskLimits, initial_equity: float):
        if initial_equity <= 0:
            raise ValueError("initial_equity must be positive")
        self.limits = limits
        self.peak_equity = initial_equity
        self._last_order_at: Optional[float] = None

    # ---- 1. hard stop-loss (tick-level, independent of candle closes) ----

    def check_hard_stop_loss(self, entry_price: float, stop_loss_pct: float, current_price: float) -> bool:
        """True if `current_price` has breached the position's stop-loss
        level. Long-only, matching `freqpanda_strategy`'s own model.
        """
        stop_price = entry_price * (1 - stop_loss_pct)
        return current_price <= stop_price

    # ---- 2. max-drawdown circuit breaker ----

    def update_equity(self, equity: float) -> None:
        """Call on every equity change (a fill, a mark-to-market update).
        Raises `CircuitBreakerTripped` once drawdown from peak equity
        reaches `max_drawdown_pct` -- the caller is expected to stop
        trading immediately when this raises, not catch-and-continue.
        """
        if equity > self.peak_equity:
            self.peak_equity = equity
        drawdown = (self.peak_equity - equity) / self.peak_equity
        if drawdown >= self.limits.max_drawdown_pct:
            raise CircuitBreakerTripped(
                f"Drawdown {drawdown:.1%} from peak equity {self.peak_equity:.2f} "
                f"(current {equity:.2f}) reached the {self.limits.max_drawdown_pct:.1%} limit"
            )

    # ---- 3. order sanity checks ----

    def check_order(
        self,
        *,
        quantity: float,
        price: float,
        equity: float,
        reference_price: Optional[float],
        now: Optional[float] = None,
    ) -> None:
        """Raises `OrderRejected` if the order looks wrong before it's ever
        sent to an exchange. `reference_price` is the last known market
        price (e.g. the latest candle close) to sanity-check `price`
        against; `now` (a `time.monotonic()`-style timestamp) is used for
        the minimum-spacing check when provided.
        """
        if quantity <= 0:
            raise OrderRejected(f"Order quantity must be positive, got {quantity}")
        if price <= 0:
            raise OrderRejected(f"Order price must be positive, got {price}")

        notional = quantity * price
        max_notional = equity * self.limits.max_position_notional_pct
        if notional > max_notional:
            raise OrderRejected(
                f"Order notional {notional:.2f} exceeds {self.limits.max_position_notional_pct:.0%} "
                f"of equity ({max_notional:.2f})"
            )

        if reference_price is not None and reference_price > 0:
            deviation = abs(price - reference_price) / reference_price
            if deviation > self.limits.max_price_deviation_pct:
                raise OrderRejected(
                    f"Order price {price} deviates {deviation:.1%} from reference price "
                    f"{reference_price}, exceeding the {self.limits.max_price_deviation_pct:.0%} limit"
                )

        if now is not None and self._last_order_at is not None:
            elapsed = now - self._last_order_at
            if elapsed < self.limits.min_seconds_between_orders:
                raise OrderRejected(
                    f"Only {elapsed:.2f}s since the last order, below the "
                    f"{self.limits.min_seconds_between_orders}s minimum spacing"
                )

        if now is not None:
            self._last_order_at = now
