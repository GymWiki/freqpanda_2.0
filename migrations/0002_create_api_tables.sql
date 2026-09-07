-- Phase 5: strategy storage + job queue bookkeeping + job results.
--
-- Run this against the same Supabase Postgres database as
-- 0001_create_ohlcv_candles.sql, e.g.:
--   psql "$SUPABASE_DB_URL" -f migrations/0002_create_api_tables.sql
--
-- Job ids are plain text (Python-generated UUID4 strings, see
-- freqpanda_api/repositories/jobs.py) rather than a Postgres-generated
-- uuid, so nothing here depends on the pgcrypto/uuid-ossp extension being
-- enabled on the target project.

create table if not exists strategies (
    id text primary key,
    name text not null,
    definition jsonb not null,
    -- Identifies which API key created this row (sha256 hex digest of the
    -- key, never the raw key itself) -- see freqpanda_api/auth.py. A
    -- single-tenant deployment can ignore this column entirely; a
    -- multi-user upgrade turns it into a real foreign key to a `users`
    -- table without changing anything that reads/writes it today, since
    -- callers already treat it as an opaque "owner identifier" string.
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (created_by, name)
);

create table if not exists jobs (
    id text primary key,
    job_type text not null check (job_type in ('backtest', 'optimization')),
    status text not null default 'pending' check (status in ('pending', 'running', 'completed', 'failed')),
    strategy_id text not null references strategies(id) on delete cascade,
    payload jsonb not null,
    error text,
    created_by text not null,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    finished_at timestamptz
);

create index if not exists jobs_strategy_id_idx on jobs (strategy_id, job_type, created_at desc);

-- One row per completed backtest job. `metrics`/`trades`/`equity_curve`
-- store BacktestResult.metrics_dict()/.trade_records()/.equity_curve_records()
-- as-is: phase 3 already produces exactly the JSON-serializable shape a
-- dashboard wants, so there is no relational trade/equity schema to design
-- or keep in sync here. The trade-off is that cross-backtest SQL analytics
-- (e.g. "average win rate across all runs of strategy X") need `->>`/`->`
-- jsonb operators instead of a plain column -- acceptable for phase 5's
-- scope; a dedicated `backtest_trades` table is the natural next step if
-- that kind of query becomes common (see the README).
create table if not exists backtest_results (
    job_id text primary key references jobs(id) on delete cascade,
    strategy_id text not null references strategies(id) on delete cascade,
    metrics jsonb not null,
    trades jsonb not null,
    equity_curve jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists backtest_results_strategy_id_idx on backtest_results (strategy_id, created_at desc);

-- One row per completed optimization job. `windows` is the per-window
-- in-sample/out-of-sample table from
-- freqpanda_optimize.OptimizationResult.summary(), plus each window's best
-- params; `final_definition`/`final_params` come from
-- freqpanda_optimize.refit_on_full_history(), run once after the
-- walk-forward validation completes.
create table if not exists optimization_results (
    job_id text primary key references jobs(id) on delete cascade,
    strategy_id text not null references strategies(id) on delete cascade,
    metric text not null,
    windows jsonb not null,
    mean_in_sample_score double precision,
    mean_out_of_sample_score double precision,
    final_params jsonb not null,
    final_definition jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists optimization_results_strategy_id_idx on optimization_results (strategy_id, created_at desc);
