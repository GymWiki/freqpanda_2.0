-- Phase 7: live/paper execution -- bot configs, encrypted exchange
-- credentials, mutable runtime state, executed trades, and an audit log.
--
-- Run against the same Supabase Postgres database as the earlier
-- migrations:
--   psql "$SUPABASE_DB_URL" -f migrations/0003_create_execution_tables.sql

-- Encrypted exchange API credentials. `encrypted_*` columns hold Fernet
-- ciphertext (see freqpanda_execution/crypto.py) produced with a master key
-- that lives only in the process environment (EXECUTION_MASTER_KEY),
-- never in this database. Losing that key makes every row here
-- permanently undecryptable -- that is intentional (see the phase-7
-- README's key rotation section), not a bug to route around by weakening
-- the encryption.
create table if not exists exchange_credentials (
    id text primary key,
    created_by text not null,
    exchange_id text not null,
    label text not null,
    encrypted_api_key text not null,
    encrypted_api_secret text not null,
    -- Some exchanges (OKX, KuCoin, ...) require a third "passphrase" secret
    -- alongside key+secret; null for exchanges that don't.
    encrypted_password text,
    created_at timestamptz not null default now(),
    unique (created_by, label)
);

-- One row per bot = (strategy, symbol, timeframe, exchange account, mode).
-- `desired_status` is what the user asked for (set via the API);
-- `status` is what is actually happening, reported by the supervisor/bot
-- process itself. Keeping these separate turns "start/stop a bot" into a
-- plain reconciliation loop (desired vs. actual) instead of the API
-- needing to reach into another process directly.
create table if not exists bots (
    id text primary key,
    name text not null,
    strategy_id text not null references strategies(id) on delete cascade,
    exchange_id text not null,
    symbol text not null,
    timeframe text not null,

    mode text not null check (mode in ('paper', 'live')),
    -- Required for live (real orders need real credentials), forbidden for
    -- paper (a paper bot has no business holding exchange API keys at all).
    credential_id text references exchange_credentials(id),
    constraint bots_live_requires_credential check (
        (mode = 'live' and credential_id is not null) or
        (mode = 'paper' and credential_id is null)
    ),

    initial_capital double precision not null check (initial_capital > 0),
    fee_pct double precision not null default 0.001 check (fee_pct >= 0),
    -- Paper-only: simulated slippage on fills. Ignored in live mode, where
    -- the exchange's own fill price is the fill price.
    slippage_pct double precision not null default 0 check (slippage_pct >= 0),

    -- Risk middleware limits (freqpanda_execution/risk.py) -- independent
    -- of the strategy's own risk_management block in the schema.
    max_drawdown_pct double precision not null check (max_drawdown_pct > 0 and max_drawdown_pct < 1),
    max_position_notional_pct double precision not null default 1.0 check (max_position_notional_pct > 0),
    max_price_deviation_pct double precision not null default 0.10 check (max_price_deviation_pct > 0),

    desired_status text not null default 'stopped' check (desired_status in ('running', 'stopped')),
    status text not null default 'stopped'
        check (status in ('stopped', 'starting', 'running', 'stopping', 'error', 'circuit_broken')),
    status_message text,

    created_by text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists bots_created_by_idx on bots (created_by, created_at desc);
create index if not exists bots_desired_status_idx on bots (desired_status);

-- Mutable runtime state, updated frequently (every candle, every price
-- tick) -- kept separate from `bots` so hammering this table with updates
-- never touches the (much less frequently written) bot configuration row.
create table if not exists bot_state (
    bot_id text primary key references bots(id) on delete cascade,
    equity double precision not null,
    peak_equity double precision not null,
    -- {entry_time, entry_price, quantity, highest_since_entry} or null when flat.
    position jsonb,
    last_price double precision,
    last_heartbeat_at timestamptz,
    updated_at timestamptz not null default now()
);

-- Completed round-trip trades (mirrors freqpanda_strategy.Trade +
-- freqpanda_backtest's cost-adjustment shape), for both paper and live --
-- `entry_order_id`/`exit_order_id` are populated only in live mode.
create table if not exists bot_trades (
    id text primary key,
    bot_id text not null references bots(id) on delete cascade,
    entry_time timestamptz not null,
    exit_time timestamptz not null,
    entry_price double precision not null,
    exit_price double precision not null,
    quantity double precision not null,
    exit_reason text not null,
    net_pnl_pct double precision not null,
    net_pnl_abs double precision not null,
    entry_order_id text,
    exit_order_id text,
    created_at timestamptz not null default now()
);

create index if not exists bot_trades_bot_id_idx on bot_trades (bot_id, exit_time desc);

-- Audit/event log: every state transition, risk-middleware intervention,
-- and error, so "why did my bot stop trading at 3am" always has an answer
-- in the database instead of only in a log file that may have rotated away.
create table if not exists bot_events (
    id bigserial primary key,
    bot_id text not null references bots(id) on delete cascade,
    event_type text not null check (event_type in (
        'started', 'stopped', 'entry', 'exit', 'hard_stop_loss',
        'circuit_breaker', 'order_rejected', 'error'
    )),
    message text not null,
    data jsonb,
    created_at timestamptz not null default now()
);

create index if not exists bot_events_bot_id_idx on bot_events (bot_id, created_at desc);
