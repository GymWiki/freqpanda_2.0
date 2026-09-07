-- Phase 2: OHLCV candle storage.
--
-- One row per (exchange, symbol, timeframe, timestamp) candle. `exchange`
-- is part of the key even though phase 2 only wires up one exchange,
-- because it is free to add now and avoids a painful migration the first
-- time a second exchange is added.
--
-- Run this against your Supabase project's Postgres database, e.g. via the
-- Supabase SQL editor or `psql "$SUPABASE_DB_URL" -f migrations/0001_create_ohlcv_candles.sql`.

create table if not exists ohlcv_candles (
    id bigserial primary key,
    exchange text not null,
    symbol text not null,
    timeframe text not null,
    timestamp timestamptz not null,
    open double precision not null,
    high double precision not null,
    low double precision not null,
    close double precision not null,
    volume double precision not null,
    inserted_at timestamptz not null default now(),

    -- Prevents duplicate candles: re-fetching an overlapping range is safe
    -- (the pipeline upserts on this key instead of inserting duplicates).
    -- This constraint's backing index also serves the "latest stored
    -- timestamp" lookup and the ranged read in fetch_ohlcv_dataframe(), so
    -- no separate index is needed.
    constraint ohlcv_candles_unique unique (exchange, symbol, timeframe, timestamp)
);
