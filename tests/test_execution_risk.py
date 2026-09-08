import pytest

from freqpanda_execution.risk import (
    CircuitBreakerTripped,
    OrderRejected,
    RiskLimits,
    RiskMiddleware,
)


def _middleware(**overrides):
    defaults = dict(max_drawdown_pct=0.2, max_position_notional_pct=1.0, max_price_deviation_pct=0.10)
    defaults.update(overrides)
    return RiskMiddleware(RiskLimits(**defaults), initial_equity=1000.0)


# ---- RiskLimits validation ----


def test_risk_limits_rejects_out_of_range_drawdown():
    with pytest.raises(ValueError):
        RiskLimits(max_drawdown_pct=0)
    with pytest.raises(ValueError):
        RiskLimits(max_drawdown_pct=1)


def test_risk_limits_rejects_non_positive_notional_and_deviation():
    with pytest.raises(ValueError):
        RiskLimits(max_drawdown_pct=0.2, max_position_notional_pct=0)
    with pytest.raises(ValueError):
        RiskLimits(max_drawdown_pct=0.2, max_price_deviation_pct=0)


def test_risk_limits_rejects_negative_min_spacing():
    with pytest.raises(ValueError):
        RiskLimits(max_drawdown_pct=0.2, min_seconds_between_orders=-1)


def test_risk_middleware_rejects_non_positive_initial_equity():
    with pytest.raises(ValueError):
        RiskMiddleware(RiskLimits(max_drawdown_pct=0.2), initial_equity=0)


# ---- 1. hard stop-loss ----


def test_hard_stop_loss_triggers_when_price_breaches_level():
    middleware = _middleware()
    assert middleware.check_hard_stop_loss(entry_price=100, stop_loss_pct=0.02, current_price=98) is True


def test_hard_stop_loss_triggers_exactly_at_level():
    middleware = _middleware()
    assert middleware.check_hard_stop_loss(entry_price=100, stop_loss_pct=0.02, current_price=98.0) is True


def test_hard_stop_loss_does_not_trigger_above_level():
    middleware = _middleware()
    assert middleware.check_hard_stop_loss(entry_price=100, stop_loss_pct=0.02, current_price=99) is False


# ---- 2. max-drawdown circuit breaker ----


def test_circuit_breaker_does_not_trip_within_limit():
    middleware = _middleware(max_drawdown_pct=0.2)
    middleware.update_equity(950.0)  # -5%, within the 20% limit
    assert middleware.peak_equity == 1000.0


def test_circuit_breaker_trips_once_drawdown_reaches_limit():
    middleware = _middleware(max_drawdown_pct=0.2)
    with pytest.raises(CircuitBreakerTripped):
        middleware.update_equity(800.0)  # exactly -20% from peak


def test_circuit_breaker_tracks_a_rising_peak_before_tripping():
    middleware = _middleware(max_drawdown_pct=0.2)
    middleware.update_equity(1200.0)
    assert middleware.peak_equity == 1200.0
    middleware.update_equity(1000.0)  # -16.7% from the new peak, still within limit
    with pytest.raises(CircuitBreakerTripped):
        middleware.update_equity(960.0)  # -20% from the 1200 peak, not the original 1000


def test_circuit_breaker_message_names_the_drawdown_and_limit():
    middleware = _middleware(max_drawdown_pct=0.2)
    with pytest.raises(CircuitBreakerTripped, match="20.0%"):
        middleware.update_equity(800.0)


# ---- 3. order sanity checks ----


def test_check_order_accepts_a_sane_order():
    middleware = _middleware()
    middleware.check_order(quantity=1.0, price=100.0, equity=1000.0, reference_price=100.0)


def test_check_order_rejects_non_positive_quantity():
    middleware = _middleware()
    with pytest.raises(OrderRejected):
        middleware.check_order(quantity=0, price=100.0, equity=1000.0, reference_price=100.0)
    with pytest.raises(OrderRejected):
        middleware.check_order(quantity=-1, price=100.0, equity=1000.0, reference_price=100.0)


def test_check_order_rejects_non_positive_price():
    middleware = _middleware()
    with pytest.raises(OrderRejected):
        middleware.check_order(quantity=1.0, price=0, equity=1000.0, reference_price=100.0)


def test_check_order_rejects_oversized_notional():
    middleware = _middleware(max_position_notional_pct=1.0)
    with pytest.raises(OrderRejected, match="notional"):
        middleware.check_order(quantity=20.0, price=100.0, equity=1000.0, reference_price=100.0)


def test_check_order_rejects_price_deviating_from_reference():
    middleware = _middleware(max_price_deviation_pct=0.10)
    with pytest.raises(OrderRejected, match="deviates"):
        middleware.check_order(quantity=1.0, price=130.0, equity=1000.0, reference_price=100.0)


def test_check_order_allows_price_within_deviation_band():
    middleware = _middleware(max_price_deviation_pct=0.10)
    middleware.check_order(quantity=1.0, price=105.0, equity=1000.0, reference_price=100.0)


def test_check_order_skips_deviation_check_without_a_reference_price():
    middleware = _middleware(max_price_deviation_pct=0.10)
    middleware.check_order(quantity=1.0, price=1000.0, equity=1_000_000.0, reference_price=None)


def test_check_order_rejects_orders_placed_too_close_together():
    middleware = _middleware(min_seconds_between_orders=5.0)
    middleware.check_order(quantity=1.0, price=100.0, equity=1000.0, reference_price=100.0, now=100.0)
    with pytest.raises(OrderRejected, match="minimum spacing"):
        middleware.check_order(quantity=1.0, price=100.0, equity=1000.0, reference_price=100.0, now=102.0)


def test_check_order_allows_orders_spaced_far_enough_apart():
    middleware = _middleware(min_seconds_between_orders=5.0)
    middleware.check_order(quantity=1.0, price=100.0, equity=1000.0, reference_price=100.0, now=100.0)
    middleware.check_order(quantity=1.0, price=100.0, equity=1000.0, reference_price=100.0, now=106.0)


def test_check_order_without_now_never_enforces_spacing():
    middleware = _middleware(min_seconds_between_orders=5.0)
    middleware.check_order(quantity=1.0, price=100.0, equity=1000.0, reference_price=100.0)
    middleware.check_order(quantity=1.0, price=100.0, equity=1000.0, reference_price=100.0)
