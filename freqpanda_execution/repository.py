"""DB access for phase 7's tables: encrypted exchange credentials, bot
configuration, mutable runtime state, executed trades, and the audit-event
log. Same direct-psycopg2 approach as `freqpanda_data`/`freqpanda_api` (see
their READMEs for why) -- and the same owner-scoping convention (every
read/write scoped by `created_by`, except the handful of "unscoped" lookups
the bot process/supervisor itself needs, since it isn't acting on behalf of
an API caller).

`freqpanda_api` depends on this module for its bots router; this module
does not depend on `freqpanda_api` -- the execution engine has to work as a
standalone worker process regardless of whether the API is even running.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json

from freqpanda_strategy import StrategyDefinition

from .crypto import decrypt_secret, encrypt_secret
from .ids import new_id


def get_strategy_definition(conn, strategy_id: str) -> Optional[StrategyDefinition]:
    """Unscoped by design -- like `get_bot_unscoped`, this is read by the
    bot process for the exact strategy its own (already-owner-scoped) bot
    row points to, not on behalf of an API caller. Mirrors
    `freqpanda_api.repositories.strategies`'s own row-to-definition parsing.
    """
    with conn.cursor() as cur:
        cur.execute("select definition from strategies where id = %s", (strategy_id,))
        row = cur.fetchone()
    if row is None:
        return None
    return StrategyDefinition.model_validate(row[0])


def _json_safe(value: Any) -> Any:
    """Postgres jsonb rejects the non-standard Infinity/NaN tokens
    `json.dumps` emits for non-finite floats -- see
    `freqpanda_api.repositories.results` for the same fix applied there.
    Recursively swaps them for `None` before they reach `Json(...)`.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


# ---- exchange credentials ----


@dataclass(frozen=True)
class CredentialSummary:
    """Never carries key material -- what a listing endpoint may return."""

    id: str
    exchange_id: str
    label: str
    created_at: dt.datetime


@dataclass(frozen=True)
class DecryptedCredential:
    """Only ever constructed at the one call site that authenticates a CCXT
    client (`freqpanda_execution.broker.LiveBroker`); never serialized.
    """

    exchange_id: str
    api_key: str
    api_secret: str
    password: Optional[str]


def create_credential(
    conn,
    created_by: str,
    exchange_id: str,
    label: str,
    api_key: str,
    api_secret: str,
    password: Optional[str] = None,
) -> CredentialSummary:
    credential_id = new_id("cred")
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into exchange_credentials
                (id, created_by, exchange_id, label, encrypted_api_key, encrypted_api_secret, encrypted_password)
            values (%s, %s, %s, %s, %s, %s, %s)
            returning id, exchange_id, label, created_at
            """,
            (
                credential_id,
                created_by,
                exchange_id,
                label,
                encrypt_secret(api_key),
                encrypt_secret(api_secret),
                encrypt_secret(password) if password else None,
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return CredentialSummary(*row)


def list_credentials(conn, created_by: str) -> List[CredentialSummary]:
    with conn.cursor() as cur:
        cur.execute(
            "select id, exchange_id, label, created_at from exchange_credentials "
            "where created_by = %s order by created_at desc",
            (created_by,),
        )
        rows = cur.fetchall()
    return [CredentialSummary(*row) for row in rows]


def delete_credential(conn, credential_id: str, created_by: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "delete from exchange_credentials where id = %s and created_by = %s",
            (credential_id, created_by),
        )
        deleted = cur.rowcount > 0
    conn.commit()
    return deleted


def get_decrypted_credential(conn, credential_id: str) -> Optional[DecryptedCredential]:
    """Unscoped by design -- called only by the bot process for the exact
    credential its own (already-owner-scoped) bot row points to.
    """
    with conn.cursor() as cur:
        cur.execute(
            "select exchange_id, encrypted_api_key, encrypted_api_secret, encrypted_password "
            "from exchange_credentials where id = %s",
            (credential_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    exchange_id, enc_key, enc_secret, enc_password = row
    return DecryptedCredential(
        exchange_id=exchange_id,
        api_key=decrypt_secret(enc_key),
        api_secret=decrypt_secret(enc_secret),
        password=decrypt_secret(enc_password) if enc_password else None,
    )


# ---- bots ----

_BOT_COLUMNS = """
    id, name, strategy_id, exchange_id, symbol, timeframe, mode, credential_id,
    initial_capital, fee_pct, slippage_pct, max_drawdown_pct, max_position_notional_pct,
    max_price_deviation_pct, desired_status, status, status_message, created_by,
    created_at, updated_at
"""


@dataclass(frozen=True)
class BotRecord:
    id: str
    name: str
    strategy_id: str
    exchange_id: str
    symbol: str
    timeframe: str
    mode: str
    credential_id: Optional[str]
    initial_capital: float
    fee_pct: float
    slippage_pct: float
    max_drawdown_pct: float
    max_position_notional_pct: float
    max_price_deviation_pct: float
    desired_status: str
    status: str
    status_message: Optional[str]
    created_by: str
    created_at: dt.datetime
    updated_at: dt.datetime


def _row_to_bot(row) -> BotRecord:
    return BotRecord(*row)


def create_bot(conn, created_by: str, **fields) -> BotRecord:
    bot_id = new_id("bot")
    columns = [
        "name", "strategy_id", "exchange_id", "symbol", "timeframe", "mode", "credential_id",
        "initial_capital", "fee_pct", "slippage_pct", "max_drawdown_pct",
        "max_position_notional_pct", "max_price_deviation_pct",
    ]
    values = [fields[c] for c in columns]
    placeholders = ", ".join(["%s"] * len(columns))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            insert into bots (id, {", ".join(columns)}, created_by)
            values (%s, {placeholders}, %s)
            returning {_BOT_COLUMNS}
            """,
            [bot_id, *values, created_by],
        )
        row = cur.fetchone()
    conn.commit()
    return _row_to_bot(row)


def get_bot(conn, bot_id: str, created_by: str) -> Optional[BotRecord]:
    with conn.cursor() as cur:
        cur.execute(
            f"select {_BOT_COLUMNS} from bots where id = %s and created_by = %s", (bot_id, created_by)
        )
        row = cur.fetchone()
    return _row_to_bot(row) if row else None


def get_bot_unscoped(conn, bot_id: str) -> Optional[BotRecord]:
    """Used by the runner/supervisor, which acts on behalf of the system,
    not a particular API caller.
    """
    with conn.cursor() as cur:
        cur.execute(f"select {_BOT_COLUMNS} from bots where id = %s", (bot_id,))
        row = cur.fetchone()
    return _row_to_bot(row) if row else None


def list_bots(conn, created_by: str) -> List[BotRecord]:
    with conn.cursor() as cur:
        cur.execute(
            f"select {_BOT_COLUMNS} from bots where created_by = %s order by created_at desc", (created_by,)
        )
        rows = cur.fetchall()
    return [_row_to_bot(row) for row in rows]


def list_bots_by_desired_status(conn, desired_status: str) -> List[BotRecord]:
    """Unscoped -- the supervisor reconciles every user's bots."""
    with conn.cursor() as cur:
        cur.execute(f"select {_BOT_COLUMNS} from bots where desired_status = %s", (desired_status,))
        rows = cur.fetchall()
    return [_row_to_bot(row) for row in rows]


def set_desired_status(conn, bot_id: str, created_by: str, desired_status: str) -> Optional[BotRecord]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            update bots set desired_status = %s, updated_at = now()
            where id = %s and created_by = %s
            returning {_BOT_COLUMNS}
            """,
            (desired_status, bot_id, created_by),
        )
        row = cur.fetchone()
    conn.commit()
    return _row_to_bot(row) if row else None


def update_status(conn, bot_id: str, status: str, message: Optional[str] = None) -> None:
    """Unscoped -- called by the bot process/supervisor about itself."""
    with conn.cursor() as cur:
        cur.execute(
            "update bots set status = %s, status_message = %s, updated_at = now() where id = %s",
            (status, message, bot_id),
        )
    conn.commit()


def delete_bot(conn, bot_id: str, created_by: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("delete from bots where id = %s and created_by = %s", (bot_id, created_by))
        deleted = cur.rowcount > 0
    conn.commit()
    return deleted


# ---- bot_state ----


@dataclass(frozen=True)
class BotState:
    bot_id: str
    equity: float
    peak_equity: float
    position: Optional[Dict[str, Any]]
    last_price: Optional[float]
    last_heartbeat_at: Optional[dt.datetime]
    updated_at: dt.datetime


def upsert_state(
    conn,
    bot_id: str,
    equity: float,
    peak_equity: float,
    position: Optional[Dict[str, Any]],
    last_price: Optional[float],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into bot_state (bot_id, equity, peak_equity, position, last_price, last_heartbeat_at)
            values (%s, %s, %s, %s, %s, now())
            on conflict (bot_id) do update set
                equity = excluded.equity, peak_equity = excluded.peak_equity,
                position = excluded.position, last_price = excluded.last_price,
                last_heartbeat_at = now(), updated_at = now()
            """,
            (bot_id, equity, peak_equity, Json(_json_safe(position)) if position is not None else None, last_price),
        )
    conn.commit()


def heartbeat(conn, bot_id: str) -> None:
    """Cheap "still alive" ping, for candle-to-candle gaps between real
    state changes (see Settings.heartbeat_interval_seconds).
    """
    with conn.cursor() as cur:
        cur.execute("update bot_state set last_heartbeat_at = now() where bot_id = %s", (bot_id,))
    conn.commit()


def get_state(conn, bot_id: str, created_by: str) -> Optional[BotState]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select s.bot_id, s.equity, s.peak_equity, s.position, s.last_price,
                   s.last_heartbeat_at, s.updated_at
            from bot_state s
            join bots b on b.id = s.bot_id
            where s.bot_id = %s and b.created_by = %s
            """,
            (bot_id, created_by),
        )
        row = cur.fetchone()
    return BotState(*row) if row else None


# ---- bot_trades ----


def record_trade(
    conn,
    bot_id: str,
    entry_time: dt.datetime,
    exit_time: dt.datetime,
    entry_price: float,
    exit_price: float,
    quantity: float,
    exit_reason: str,
    net_pnl_pct: float,
    net_pnl_abs: float,
    entry_order_id: Optional[str] = None,
    exit_order_id: Optional[str] = None,
) -> str:
    trade_id = new_id("bottrade")
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into bot_trades
                (id, bot_id, entry_time, exit_time, entry_price, exit_price, quantity,
                 exit_reason, net_pnl_pct, net_pnl_abs, entry_order_id, exit_order_id)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                trade_id, bot_id, entry_time, exit_time, entry_price, exit_price, quantity,
                exit_reason, net_pnl_pct, net_pnl_abs, entry_order_id, exit_order_id,
            ),
        )
    conn.commit()
    return trade_id


def list_trades(conn, bot_id: str, created_by: str, limit: int = 200) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select t.entry_time, t.exit_time, t.entry_price, t.exit_price, t.quantity,
                   t.exit_reason, t.net_pnl_pct, t.net_pnl_abs, t.entry_order_id, t.exit_order_id
            from bot_trades t
            join bots b on b.id = t.bot_id
            where t.bot_id = %s and b.created_by = %s
            order by t.exit_time desc
            limit %s
            """,
            (bot_id, created_by, limit),
        )
        rows = cur.fetchall()
    columns = [
        "entry_time", "exit_time", "entry_price", "exit_price", "quantity",
        "exit_reason", "net_pnl_pct", "net_pnl_abs", "entry_order_id", "exit_order_id",
    ]
    return [dict(zip(columns, row)) for row in rows]


# ---- bot_events ----


def record_event(conn, bot_id: str, event_type: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "insert into bot_events (bot_id, event_type, message, data) values (%s, %s, %s, %s)",
            (bot_id, event_type, message, Json(_json_safe(data)) if data is not None else None),
        )
    conn.commit()


def list_events(conn, bot_id: str, created_by: str, limit: int = 100) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select e.event_type, e.message, e.data, e.created_at
            from bot_events e
            join bots b on b.id = e.bot_id
            where e.bot_id = %s and b.created_by = %s
            order by e.created_at desc
            limit %s
            """,
            (bot_id, created_by, limit),
        )
        rows = cur.fetchall()
    return [
        {"event_type": event_type, "message": message, "data": data, "created_at": created_at}
        for event_type, message, data, created_at in rows
    ]
