-- freqpanda: volledige Supabase-setup in één keer.
--
-- Combineert migraties 0001 t/m 0003 (OHLCV-opslag, API/job-tabellen,
-- executie-tabellen) tot één script. Bedoeld om in de Supabase SQL Editor
-- te plakken en in één keer uit te voeren op een lege database, of via:
--   psql "$SUPABASE_DB_URL" -f migrations/supabase_setup.sql
--
-- Idempotent: elke `create table`/`create index` gebruikt `if not exists`,
-- dus dit script nogmaals draaien op een database die al is opgezet doet
-- niets kapot. Bij nieuwe fases komen er losse, genummerde migraties bij
-- (`migrations/000N_*.sql`) — dit bestand is alleen de gebundelde
-- snelstart voor een verse database en wordt niet automatisch bijgewerkt;
-- check bij een upgrade van een bestaand project of er nieuwere
-- genummerde migraties zijn die hier nog niet in zitten.

-- ============================================================
-- Fase 2: OHLCV candle-opslag
-- ============================================================

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

    -- Voorkomt dubbele candles: een overlappend bereik opnieuw ophalen is
    -- veilig (de pipeline doet een upsert op deze key i.p.v. dubbel in te
    -- voegen). De index achter deze constraint bedient ook de "laatst
    -- opgeslagen timestamp"-lookup en het ranged-read in
    -- fetch_ohlcv_dataframe(), dus is er geen aparte index nodig.
    constraint ohlcv_candles_unique unique (exchange, symbol, timeframe, timestamp)
);

-- ============================================================
-- Fase 5: strategie-opslag + job-queue + resultaten
-- ============================================================
--
-- Job-id's zijn platte tekst (Python-gegenereerde UUID4-strings, zie
-- freqpanda_api/repositories/jobs.py) in plaats van een door Postgres
-- gegenereerde uuid, zodat niets hier afhankelijk is van de
-- pgcrypto/uuid-ossp-extensie op het doelproject.

create table if not exists strategies (
    id text primary key,
    name text not null,
    definition jsonb not null,
    -- Identificeert welke API-key deze rij aanmaakte (sha256 hex digest van
    -- de key, nooit de key zelf) -- zie freqpanda_api/auth.py. Een
    -- single-tenant deployment mag deze kolom negeren; een upgrade naar
    -- echte gebruikersaccounts maakt er een echte foreign key naar een
    -- `users`-tabel van zonder iets te breken dat 'm vandaag al leest/schrijft,
    -- want elke aanroeper behandelt 'm al als een ondoorzichtige
    -- "eigenaar-identifier"-string.
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

-- Eén rij per afgeronde backtest-job. `metrics`/`trades`/`equity_curve`
-- slaan BacktestResult.metrics_dict()/.trade_records()/.equity_curve_records()
-- ongewijzigd op: fase 3 levert al precies de JSON-serialiseerbare vorm die
-- een dashboard nodig heeft, dus hoeft hier geen relationeel trade/equity-
-- schema ontworpen of gesynchroniseerd te worden.
create table if not exists backtest_results (
    job_id text primary key references jobs(id) on delete cascade,
    strategy_id text not null references strategies(id) on delete cascade,
    metrics jsonb not null,
    trades jsonb not null,
    equity_curve jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists backtest_results_strategy_id_idx on backtest_results (strategy_id, created_at desc);

-- Eén rij per afgeronde optimalisatie-job. `windows` is de per-venster
-- in-sample/out-of-sample-tabel uit
-- freqpanda_optimize.OptimizationResult.summary(), plus de beste params per
-- venster; `final_definition`/`final_params` komen uit
-- freqpanda_optimize.refit_on_full_history(), eenmalig gedraaid na afloop
-- van de walk-forward-validatie.
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

-- ============================================================
-- Fase 7: live/paper executie -- bot-configs, versleutelde
-- exchange-credentials, runtime-state, trades, audit-log
-- ============================================================

-- Versleutelde exchange-API-credentials. `encrypted_*`-kolommen bevatten
-- Fernet-ciphertext (zie freqpanda_execution/crypto.py), gemaakt met een
-- master key die uitsluitend in de procesomgeving leeft
-- (EXECUTION_MASTER_KEY), nooit in deze database. Die key kwijtraken maakt
-- elke rij hier permanent onleesbaar -- dat is bedoeld gedrag (zie de
-- fase-7-README), geen bug om omheen te werken door de encryptie te
-- verzwakken.
create table if not exists exchange_credentials (
    id text primary key,
    created_by text not null,
    exchange_id text not null,
    label text not null,
    encrypted_api_key text not null,
    encrypted_api_secret text not null,
    -- Sommige exchanges (OKX, KuCoin, ...) vereisen een derde
    -- "passphrase"-secret naast key+secret; null voor exchanges zonder.
    encrypted_password text,
    created_at timestamptz not null default now(),
    unique (created_by, label)
);

-- Eén rij per bot = (strategie, symbool, timeframe, exchange-account, mode).
-- `desired_status` is wat de gebruiker heeft aangevraagd (via de API);
-- `status` is wat er werkelijk gebeurt, gerapporteerd door de
-- supervisor/het bot-proces zelf. Door deze twee gescheiden te houden wordt
-- "start/stop een bot" een simpele reconciliatie-loop (gewenst vs. actueel)
-- in plaats van dat de API rechtstreeks een ander proces moet aanspreken.
create table if not exists bots (
    id text primary key,
    name text not null,
    strategy_id text not null references strategies(id) on delete cascade,
    exchange_id text not null,
    symbol text not null,
    timeframe text not null,

    mode text not null check (mode in ('paper', 'live')),
    -- Verplicht voor live (echte orders hebben echte credentials nodig),
    -- verboden voor paper (een paper-bot heeft niets te zoeken met
    -- exchange-API-keys).
    credential_id text references exchange_credentials(id),
    constraint bots_live_requires_credential check (
        (mode = 'live' and credential_id is not null) or
        (mode = 'paper' and credential_id is null)
    ),

    initial_capital double precision not null check (initial_capital > 0),
    fee_pct double precision not null default 0.001 check (fee_pct >= 0),
    -- Alleen paper: gesimuleerde slippage op fills. Genegeerd in live mode,
    -- waar de eigen fill-prijs van de exchange de fill-prijs is.
    slippage_pct double precision not null default 0 check (slippage_pct >= 0),

    -- Risk-middleware-limieten (freqpanda_execution/risk.py) -- los van het
    -- risk_management-blok van de strategie zelf in het schema.
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

-- Mutable runtime-state, vaak geüpdatet (elke candle, elke prijstick) --
-- los van `bots` gehouden zodat dit tabel-geweld nooit de (veel minder
-- vaak geschreven) bot-configuratierij raakt.
create table if not exists bot_state (
    bot_id text primary key references bots(id) on delete cascade,
    equity double precision not null,
    peak_equity double precision not null,
    -- {entry_time, entry_price, quantity, highest_since_entry} of null als er geen positie open is.
    position jsonb,
    last_price double precision,
    last_heartbeat_at timestamptz,
    updated_at timestamptz not null default now()
);

-- Afgeronde round-trip trades (spiegelt freqpanda_strategy.Trade +
-- freqpanda_backtest's kostenaanpassing), voor zowel paper als live --
-- `entry_order_id`/`exit_order_id` alleen gevuld in live mode.
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

-- Audit-/event-log: elke statusovergang, risk-middleware-interventie en
-- fout, zodat "waarom stopte mijn bot vannacht om 3 uur met handelen"
-- altijd een antwoord heeft in de database in plaats van alleen in een
-- logbestand dat inmiddels geroteerd kan zijn.
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
