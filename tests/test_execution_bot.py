"""Bot orchestration tests: real PaperBroker/RiskMiddleware/LivePositionTracker
wired together (so the actual decision logic runs), with only the
`repository` module (the DB boundary) monkeypatched -- consistent with how
`test_api_tasks.py` exercises `freqpanda_api.jobs.tasks` for real against a
faked persistence layer.
"""
import asyncio
import datetime as dt
from unittest.mock import MagicMock

import pandas as pd
import pytest

from freqpanda_backtest.costs import TradingCosts
from freqpanda_execution import repository
from freqpanda_execution.bot import Bot
from freqpanda_execution.broker import PaperBroker
from freqpanda_execution.repository import BotRecord
from freqpanda_execution.risk import CircuitBreakerTripped, RiskLimits
from freqpanda_strategy import RiskManagement, StrategyDefinition


def _ohlcv(closes, lows=None, highs=None):
    n = len(closes)
    lows = lows or closes
    highs = highs or closes
    index = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes, "volume": [1.0] * n},
        index=index,
    )


def _definition(entry, exit_, risk):
    return StrategyDefinition(
        name="bot_test", indicators=[], entry_conditions=entry, exit_conditions=exit_,
        risk_management=RiskManagement(**risk),
    )


def _bot_record(**overrides):
    fields = dict(
        id="bot_1", name="test bot", strategy_id="strat_1", exchange_id="binance", symbol="BTC/USDT",
        timeframe="1h", mode="paper", credential_id=None, initial_capital=1000.0,
        fee_pct=0.0, slippage_pct=0.0, max_drawdown_pct=0.5, max_position_notional_pct=1.0,
        max_price_deviation_pct=0.9, desired_status="running", status="starting", status_message=None,
        created_by="owner-hash",
        created_at=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
        updated_at=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
    )
    fields.update(overrides)
    return BotRecord(**fields)


def _make_bot(definition, risk_limits=None, record_overrides=None):
    record = _bot_record(**(record_overrides or {}))
    limits = risk_limits or RiskLimits(
        max_drawdown_pct=record.max_drawdown_pct,
        max_position_notional_pct=record.max_position_notional_pct,
        max_price_deviation_pct=record.max_price_deviation_pct,
    )
    broker = PaperBroker(TradingCosts(fee_pct=record.fee_pct, slippage_pct=record.slippage_pct))
    conn = MagicMock()
    return Bot(
        conn=conn, record=record, definition=definition, broker=broker, costs=broker.costs,
        limits=limits, history=_ohlcv([100.0]),
    )


@pytest.fixture(autouse=True)
def _quiet_persistence(monkeypatch):
    """`_save_state`/heartbeat aren't under test here -- no-op them so every
    test only has to assert on the calls it actually cares about.
    """
    monkeypatch.setattr(repository, "upsert_state", lambda *a, **k: None)
    monkeypatch.setattr(repository, "heartbeat", lambda *a, **k: None)


def _capture_events(monkeypatch):
    events = []
    monkeypatch.setattr(
        repository, "record_event",
        lambda conn, bot_id, event_type, message, data=None: events.append((event_type, message, data)),
    )
    return events


def _capture_trades(monkeypatch):
    trades = []
    monkeypatch.setattr(
        repository, "record_trade",
        lambda conn, bot_id, **kwargs: (trades.append(kwargs), "bottrade_1")[1],
    )
    return trades


# ---- entry ----


def test_on_candle_close_executes_entry_and_updates_equity(monkeypatch):
    events = _capture_events(monkeypatch)
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None, risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    bot = _make_bot(definition)

    bot._on_candle_close(_ohlcv([100.0, 105.0]))

    assert bot.tracker.position is not None
    assert bot.tracker.position.entry_price == pytest.approx(105.0)
    assert bot.current_quantity == pytest.approx(1000.0 / 105.0)
    assert bot.equity == pytest.approx(1000.0)  # fully deployed, zero fees
    assert [e[0] for e in events] == ["entry"]


def test_on_candle_close_does_nothing_when_no_signal(monkeypatch):
    events = _capture_events(monkeypatch)
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 999},
        exit_=None, risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    bot = _make_bot(definition)

    bot._on_candle_close(_ohlcv([100.0, 101.0]))

    assert bot.tracker.position is None
    assert events == []


# ---- exit ----


def test_on_candle_close_closes_position_on_exit_signal(monkeypatch):
    events = _capture_events(monkeypatch)
    trades = _capture_trades(monkeypatch)
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_={"type": "comparison", "left": "close", "op": "lt", "right": 100},
        risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    bot = _make_bot(definition)

    bot._on_candle_close(_ohlcv([100.0, 105.0]))
    bot._on_candle_close(_ohlcv([100.0, 105.0, 95.0]))

    assert bot.tracker.position is None
    assert bot.current_quantity == 0.0
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "exit_signal"
    assert trades[0]["exit_price"] == pytest.approx(95.0)
    assert [e[0] for e in events] == ["entry", "exit"]


# ---- independent hard stop-loss ----


def test_hard_stop_loss_emits_its_own_event_before_the_generic_exit(monkeypatch):
    events = _capture_events(monkeypatch)
    trades = _capture_trades(monkeypatch)
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None, risk={"stop_loss_pct": 0.05, "take_profit_pct": 0.9},
    )
    bot = _make_bot(definition)

    bot._on_candle_close(_ohlcv([100.0, 105.0]))  # enters at 105
    # stop level is 105 * 0.95 = 99.75; 90 breaches it well past what the
    # interpreter's own once-per-candle stop-loss check would need.
    bot._on_candle_close(_ohlcv([100.0, 105.0, 90.0]))

    assert bot.tracker.position is None
    assert [e[0] for e in events] == ["entry", "hard_stop_loss", "exit"]
    assert trades[0]["exit_reason"] == "hard_stop_loss"
    assert trades[0]["exit_price"] == pytest.approx(90.0)


def test_hard_stop_loss_does_not_trigger_before_the_level_is_breached(monkeypatch):
    events = _capture_events(monkeypatch)
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None, risk={"stop_loss_pct": 0.05, "take_profit_pct": 0.9},
    )
    bot = _make_bot(definition)

    bot._on_candle_close(_ohlcv([100.0, 105.0]))
    bot._on_candle_close(_ohlcv([100.0, 105.0, 101.0]))  # still well above the 99.75 stop level

    assert bot.tracker.position is not None
    assert [e[0] for e in events] == ["entry"]


# ---- order sanity checks (rollback on rejection) ----


def test_order_rejected_rolls_back_the_optimistic_entry(monkeypatch):
    events = _capture_events(monkeypatch)
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None, risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    limits = RiskLimits(max_drawdown_pct=0.5, max_position_notional_pct=0.0001, max_price_deviation_pct=0.9)
    bot = _make_bot(definition, risk_limits=limits)

    bot._on_candle_close(_ohlcv([100.0, 105.0]))

    assert bot.tracker.position is None  # rolled back -- the broker never filled
    assert bot.current_quantity == 0.0
    assert bot.equity == 1000.0
    assert [e[0] for e in events] == ["order_rejected"]


# ---- max-drawdown circuit breaker ----


def test_closing_position_raises_circuit_breaker_on_large_drawdown(monkeypatch):
    _capture_events(monkeypatch)
    _capture_trades(monkeypatch)
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_={"type": "comparison", "left": "close", "op": "lt", "right": 60},
        risk={"stop_loss_pct": 0.9, "take_profit_pct": 0.9},
    )
    limits = RiskLimits(max_drawdown_pct=0.1, max_position_notional_pct=1.0, max_price_deviation_pct=0.9)
    bot = _make_bot(definition, risk_limits=limits)

    bot._on_candle_close(_ohlcv([100.0, 105.0]))  # entry at 105
    with pytest.raises(CircuitBreakerTripped):
        bot._on_candle_close(_ohlcv([100.0, 105.0, 50.0]))  # a ~52% drawdown, way past the 10% limit


# ---- run() status transitions ----


def test_run_reports_circuit_broken_status_without_propagating_normally(monkeypatch):
    events = _capture_events(monkeypatch)
    statuses = []
    monkeypatch.setattr(
        repository, "update_status",
        lambda conn, bot_id, status, message=None: statuses.append((status, message)),
    )
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None, risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    bot = _make_bot(definition)

    async def _raise(*args, **kwargs):
        raise CircuitBreakerTripped("drawdown limit reached")

    monkeypatch.setattr(bot.feed, "run", _raise)

    asyncio.run(bot.run())

    assert statuses[0] == ("running", None)
    assert statuses[-1][0] == "circuit_broken"
    assert [e[0] for e in events] == ["started", "circuit_breaker"]


def test_run_reports_error_status_and_reraises_unexpected_exceptions(monkeypatch):
    events = _capture_events(monkeypatch)
    statuses = []
    monkeypatch.setattr(
        repository, "update_status",
        lambda conn, bot_id, status, message=None: statuses.append((status, message)),
    )
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None, risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    bot = _make_bot(definition)

    async def _raise(*args, **kwargs):
        raise RuntimeError("exchange connection reset")

    monkeypatch.setattr(bot.feed, "run", _raise)

    with pytest.raises(RuntimeError, match="exchange connection reset"):
        asyncio.run(bot.run())

    assert statuses[-1][0] == "error"
    assert [e[0] for e in events] == ["started", "error"]


def test_run_reports_stopped_status_on_clean_completion(monkeypatch):
    events = _capture_events(monkeypatch)
    statuses = []
    monkeypatch.setattr(
        repository, "update_status",
        lambda conn, bot_id, status, message=None: statuses.append((status, message)),
    )
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None, risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    bot = _make_bot(definition)

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(bot.feed, "run", _noop)

    asyncio.run(bot.run())

    assert [s[0] for s in statuses] == ["running", "stopped"]
    assert [e[0] for e in events] == ["started", "stopped"]


def test_stop_sets_the_stop_event():
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None, risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    bot = _make_bot(definition)
    assert not bot.stop_event.is_set()
    bot.stop()
    assert bot.stop_event.is_set()


# ---- resume_from_state ----


def test_resume_from_state_rehydrates_open_position_and_equity():
    definition = _definition(
        entry={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        exit_=None, risk={"stop_loss_pct": 0.5, "take_profit_pct": 0.5},
    )
    bot = _make_bot(definition)
    state = repository.BotState(
        bot_id="bot_1", equity=1200.0, peak_equity=1300.0,
        position={
            "entry_time": "2024-01-01T00:00:00+00:00", "entry_price": 100.0,
            "highest_since_entry": 110.0, "quantity": 12.0,
            "equity_at_entry": 1000.0, "entry_order_id": None,
        },
        last_price=110.0, last_heartbeat_at=None,
        updated_at=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
    )

    bot.resume_from_state(state)

    assert bot.equity == 1200.0
    assert bot.risk.peak_equity == 1300.0
    assert bot.tracker.position is not None
    assert bot.tracker.position.entry_price == 100.0
    assert bot.current_quantity == 12.0
    assert bot.equity_at_entry == 1000.0
