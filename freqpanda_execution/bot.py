"""Ties the pieces together: a `RealtimeFeed` calls back into
`live_interpreter` (phase 1's own indicator/condition code) on every
closed candle; the resulting entry/exit decisions go through
`RiskMiddleware` and a `Broker` (paper or live); resulting state (equity,
open position, trades, events) is written straight to Postgres via
`repository.py`, the same place the phase-6 webapp would read it from.

One `Bot` instance is one running process's worth of work -- see
`runner.py` for the process entrypoint and `supervisor.py` for how one
bot's crash is kept from affecting any other.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

import ccxt
import pandas as pd

from freqpanda_backtest.costs import TradingCosts
from freqpanda_data.db import fetch_ohlcv_dataframe
from freqpanda_data.exchange import create_exchange
from freqpanda_strategy import StrategyDefinition

from . import repository
from .broker import Broker, LiveBroker, PaperBroker
from .feed import RealtimeFeed
from .live_interpreter import LivePositionTracker, OpenPosition, SignalSnapshot, latest_signal
from .repository import BotRecord
from .risk import CircuitBreakerTripped, OrderRejected, RiskLimits, RiskMiddleware

logger = logging.getLogger(__name__)


def _create_authenticated_exchange(exchange_id: str, api_key: str, api_secret: str, password: Optional[str]) -> ccxt.Exchange:
    exchange_class = getattr(ccxt, exchange_id)
    config = {"enableRateLimit": True, "apiKey": api_key, "secret": api_secret}
    if password:
        config["password"] = password
    return exchange_class(config)


def build_bot(conn, bot_id: str) -> "Bot":
    """Assembles a `Bot` from its stored config: strategy definition, seed
    candle history (from phase 2's storage -- never fetched live here),
    the right `Broker` for its mode, and (if this is a restart) whatever
    equity/position it last reported, so a bot resumes rather than forgets
    an open position across a process restart.
    """
    record = repository.get_bot_unscoped(conn, bot_id)
    if record is None:
        raise ValueError(f"Bot {bot_id} not found")

    definition = repository.get_strategy_definition(conn, record.strategy_id)
    if definition is None:
        raise ValueError(f"Strategy {record.strategy_id} (for bot {bot_id}) not found")

    history = fetch_ohlcv_dataframe(conn, record.exchange_id, record.symbol, record.timeframe)
    if history.empty:
        raise ValueError(
            f"No stored OHLCV data for {record.exchange_id}/{record.symbol}/{record.timeframe}. "
            "Run the phase-2 data pipeline for this pair before starting the bot."
        )

    market_data_exchange = create_exchange(record.exchange_id)
    costs = TradingCosts(fee_pct=record.fee_pct, slippage_pct=record.slippage_pct if record.mode == "paper" else 0.0)

    if record.mode == "paper":
        broker: Broker = PaperBroker(costs)
    else:
        if record.credential_id is None:
            raise ValueError(f"Live bot {bot_id} has no exchange_credential configured")
        credential = repository.get_decrypted_credential(conn, record.credential_id)
        if credential is None:
            raise ValueError(f"Credential {record.credential_id} for bot {bot_id} not found")
        live_exchange = _create_authenticated_exchange(
            credential.exchange_id, credential.api_key, credential.api_secret, credential.password
        )
        broker = LiveBroker(live_exchange)

    limits = RiskLimits(
        max_drawdown_pct=record.max_drawdown_pct,
        max_position_notional_pct=record.max_position_notional_pct,
        max_price_deviation_pct=record.max_price_deviation_pct,
    )

    bot = Bot(conn=conn, record=record, definition=definition, broker=broker, costs=costs, limits=limits, history=history)

    saved_state = repository.get_state(conn, bot_id, record.created_by)
    if saved_state is not None:
        bot.resume_from_state(saved_state)

    return bot


class Bot:
    def __init__(
        self,
        *,
        conn,
        record: BotRecord,
        definition: StrategyDefinition,
        broker: Broker,
        costs: TradingCosts,
        limits: RiskLimits,
        history: pd.DataFrame,
    ):
        self.conn = conn
        self.record = record
        self.definition = definition
        self.broker = broker
        self.costs = costs

        self.tracker = LivePositionTracker(definition.risk_management)
        self.equity = record.initial_capital
        self.equity_at_entry = record.initial_capital
        self.current_quantity = 0.0
        self.entry_order_id: Optional[str] = None
        self.risk = RiskMiddleware(limits, initial_equity=record.initial_capital)

        self.feed = RealtimeFeed(record.exchange_id, record.symbol, record.timeframe, history)
        self.exchange = create_exchange(record.exchange_id)
        self.stop_event = asyncio.Event()

    def resume_from_state(self, state: repository.BotState) -> None:
        """Rehydrate from a previous run's last reported state, so
        restarting the process doesn't forget an open position or reset
        the drawdown-tracking peak equity.
        """
        self.equity = state.equity
        self.risk.peak_equity = state.peak_equity
        if state.position is not None:
            p = state.position
            self.tracker.position = OpenPosition(
                entry_time=pd.Timestamp(p["entry_time"]),
                entry_price=p["entry_price"],
                highest_since_entry=p["highest_since_entry"],
            )
            self.current_quantity = p["quantity"]
            self.equity_at_entry = p.get("equity_at_entry", state.equity)
            self.entry_order_id = p.get("entry_order_id")
        logger.info("bot %s: resumed at equity=%.2f, in_position=%s", self.record.id, self.equity, state.position is not None)

    async def run(self) -> None:
        repository.update_status(self.conn, self.record.id, "running")
        repository.record_event(self.conn, self.record.id, "started", f"Bot started in {self.record.mode} mode")
        self._save_state()
        try:
            await self.feed.run(self.exchange, self._on_candle_close, self.stop_event)
        except CircuitBreakerTripped as exc:
            repository.update_status(self.conn, self.record.id, "circuit_broken", str(exc))
            repository.record_event(self.conn, self.record.id, "circuit_breaker", str(exc))
        except Exception as exc:  # noqa: BLE001 -- last resort: report, then re-raise for the supervisor to see
            repository.update_status(self.conn, self.record.id, "error", str(exc))
            repository.record_event(self.conn, self.record.id, "error", str(exc))
            raise
        else:
            repository.update_status(self.conn, self.record.id, "stopped")
            repository.record_event(self.conn, self.record.id, "stopped", "Bot stopped")

    def stop(self) -> None:
        self.stop_event.set()

    # ---- candle-close handling ----

    def _on_candle_close(self, history: pd.DataFrame) -> None:
        snapshot = latest_signal(self.definition, history)

        # Independent, tick-level hard stop-loss -- checked ahead of (and
        # regardless of) whatever the mirrored interpreter loop below would
        # decide. See risk.py's module docstring for why this exists even
        # though the interpreter already enforces the same stop-loss.
        position = self.tracker.position
        if position is not None and self.risk.check_hard_stop_loss(
            position.entry_price, self.definition.risk_management.stop_loss_pct, snapshot.close
        ):
            repository.record_event(
                self.conn, self.record.id, "hard_stop_loss",
                f"Independent hard stop-loss triggered at {snapshot.close:.8g} "
                f"(entry {position.entry_price:.8g})",
                {"entry_price": position.entry_price, "trigger_price": snapshot.close},
            )
            self._close_position(position, exit_price=snapshot.close, exit_reason="hard_stop_loss", exit_time=snapshot.timestamp)
            self.tracker.position = None
            self._save_state()
            return

        position_before = self.tracker.position
        action = self.tracker.process(snapshot)

        if action is None:
            repository.heartbeat(self.conn, self.record.id)
            return

        if action.kind == "enter":
            self._execute_entry(snapshot)
        else:
            self._close_position(position_before, exit_price=action.price, exit_reason=action.reason, exit_time=snapshot.timestamp)
        self._save_state()

    def _execute_entry(self, snapshot: SignalSnapshot) -> None:
        estimated_quantity = (self.equity * (1 - self.costs.fee_pct)) / snapshot.close
        try:
            self.risk.check_order(
                quantity=estimated_quantity,
                price=snapshot.close,
                equity=self.equity,
                reference_price=snapshot.close,
                now=time.monotonic(),
            )
        except OrderRejected as exc:
            repository.record_event(self.conn, self.record.id, "order_rejected", str(exc))
            self.tracker.position = None  # the tracker optimistically opened; roll it back, we never actually filled
            return

        fill = self.broker.open_long(self.record.symbol, self.equity, self.costs.fee_pct, snapshot.close)

        # Use the fill actually realized (which may differ from the
        # estimate above, especially in live mode) for all subsequent
        # stop-loss/take-profit/trailing-stop tracking.
        self.tracker.position.entry_price = fill.price
        self.tracker.position.highest_since_entry = fill.price
        self.current_quantity = fill.quantity
        self.entry_order_id = fill.order_id
        self.equity_at_entry = self.equity
        self.equity = fill.quantity * fill.price  # paper capital after paying the entry fee, mirrors freqpanda_backtest's equity curve

        repository.record_event(
            self.conn, self.record.id, "entry",
            f"Entered {self.record.symbol} at {fill.price:.8g}",
            {"price": fill.price, "quantity": fill.quantity, "order_id": fill.order_id},
        )

    def _close_position(self, position: OpenPosition, *, exit_price: float, exit_reason: str, exit_time: pd.Timestamp) -> None:
        quantity = self.current_quantity
        fill = self.broker.close_long(self.record.symbol, quantity, exit_price)

        proceeds = fill.quantity * fill.price
        equity_after = proceeds * (1 - self.costs.fee_pct)
        net_pnl_abs = equity_after - self.equity_at_entry
        net_pnl_pct = (equity_after / self.equity_at_entry) - 1

        repository.record_trade(
            self.conn,
            self.record.id,
            entry_time=position.entry_time.to_pydatetime(),
            exit_time=exit_time.to_pydatetime(),
            entry_price=position.entry_price,
            exit_price=fill.price,
            quantity=quantity,
            exit_reason=exit_reason,
            net_pnl_pct=net_pnl_pct,
            net_pnl_abs=net_pnl_abs,
            entry_order_id=self.entry_order_id,
            exit_order_id=fill.order_id,
        )
        repository.record_event(
            self.conn, self.record.id, "exit",
            f"Exited {self.record.symbol} at {fill.price:.8g} ({exit_reason}), pnl {net_pnl_pct:+.2%}",
            {"price": fill.price, "quantity": quantity, "reason": exit_reason, "order_id": fill.order_id},
        )

        self.equity = equity_after
        self.current_quantity = 0.0
        self.entry_order_id = None

        # Raises CircuitBreakerTripped if this trade's loss breaches the
        # max-drawdown limit -- propagates up through _on_candle_close and
        # run(), which reports 'circuit_broken' and stops the feed.
        self.risk.update_equity(self.equity)

    def _save_state(self) -> None:
        position_json = None
        if self.tracker.position is not None:
            p = self.tracker.position
            position_json = {
                "entry_time": p.entry_time.isoformat(),
                "entry_price": p.entry_price,
                "highest_since_entry": p.highest_since_entry,
                "quantity": self.current_quantity,
                "equity_at_entry": self.equity_at_entry,
                "entry_order_id": self.entry_order_id,
            }
        repository.upsert_state(
            self.conn,
            self.record.id,
            equity=self.equity,
            peak_equity=self.risk.peak_equity,
            position=position_json,
            last_price=float(self.feed.history["close"].iloc[-1]) if len(self.feed.history) else None,
        )
