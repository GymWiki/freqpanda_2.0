# freqpanda_data — fase 2: data-pipeline

Haalt historische en actuele OHLCV-data op via [CCXT](https://github.com/ccxt/ccxt),
slaat het incrementeel op in Supabase/Postgres, en geeft het terug als een
pandas DataFrame in **exact** het formaat dat de fase-1 interpreter
(`freqpanda_strategy.run_strategy`) verwacht: een oplopend gesorteerde
`DatetimeIndex` met float-kolommen `open`, `high`, `low`, `close`, `volume`.

Los van backtesting-logica, UI/API en live order-executie — dit levert
alleen marktdata.

## Installeren

```bash
pip install -e ".[dev]"
```

Zet de database-migratie klaar (eenmalig, tegen je Supabase Postgres):

```bash
psql "$SUPABASE_DB_URL" -f migrations/0001_create_ohlcv_candles.sql
```

## Snel starten

```bash
export SUPABASE_DB_URL="postgresql://postgres:...@....supabase.co:5432/postgres"
python scripts/run_pipeline.py config/pipeline.json
```

Elke run haalt per symbool/timeframe alleen de candles op die nog niet zijn
opgeslagen (zie "Incrementeel bijwerken" hieronder) — vaker draaien (bv. via
cron elke paar minuten) is dus goedkoop.

Data teruglezen voor de fase-1 interpreter:

```python
from freqpanda_data import get_connection, fetch_ohlcv_dataframe
from freqpanda_strategy import load_strategy_definition, run_strategy

conn = get_connection()  # leest SUPABASE_DB_URL / DATABASE_URL uit env
df = fetch_ohlcv_dataframe(conn, exchange="binance", symbol="BTC/USDT", timeframe="1h")

definition = load_strategy_definition("examples/ema_crossover.json")
trades = run_strategy(definition, df)
```

## Architectuur

```
freqpanda_data/
  config.py      PipelineConfig / SymbolTimeframe (dataclasses) + JSON-loader
  exchange.py     CCXT-wrapper: exchange aanmaken, gepagineerd historie ophalen
  db.py           Opslag: upsert in Postgres, laatste timestamp opzoeken,
                   data teruglezen als DataFrame
  pipeline.py     Orkestratie: incrementeel bijwerken per symbool/timeframe
migrations/
  0001_create_ohlcv_candles.sql   Tabel + unieke constraint
config/
  pipeline.json   Voorbeeldconfig: welke exchange/symbolen/timeframes
scripts/
  run_pipeline.py Command-line entrypoint (cron/handmatig/later job-queue)
```

## Opslagformaat

Eén tabel, `ohlcv_candles` (zie `migrations/0001_create_ohlcv_candles.sql`):

| kolom       | type          | omschrijving                                |
|-------------|---------------|----------------------------------------------|
| exchange    | text          | bv. `"binance"`                               |
| symbol      | text          | bv. `"BTC/USDT"` (CCXT-notatie)               |
| timeframe   | text          | bv. `"1h"` (CCXT-notatie)                     |
| timestamp   | timestamptz   | open-tijd van de candle (UTC)                 |
| open/high/low/close/volume | double precision | candle-data          |
| inserted_at | timestamptz   | wanneer deze rij is geschreven (audit/debug)  |

met `unique (exchange, symbol, timeframe, timestamp)` — dat is de sleutel
waarop upserts draaien, dus dubbele candles kunnen niet ontstaan.

`exchange` zit in de sleutel ook al gebruikt fase 2 er maar één (Binance):
een tweede exchange later toevoegen is dan een kwestie van meer rijen, geen
schema-migratie.

## Incrementeel bijwerken

`update_symbol_timeframe()` (in `pipeline.py`) doet per symbool/timeframe:

1. Zoek de meest recente opgeslagen candle-timestamp op
   (`get_latest_timestamp_ms`). Is er niks opgeslagen, gebruik dan
   `config.backfill_since` als startpunt (eenmalige volledige backfill).
2. Haal alleen candles op **na** die timestamp (`since = laatste + 1
   timeframe`) — nooit de hele geschiedenis opnieuw.
3. Filter de nog lopende (niet-afgesloten) candle uit elke pagina (een candle
   telt pas als afgesloten zodra `open_tijd + timeframe <= nu`) — anders zou
   je telkens een candle met halve data opslaan.
4. Upsert de rest. Bestaat een rij al (zelfde exchange/symbol/timeframe/
   timestamp), dan wordt hij overschreven in plaats van gedupliceerd — dat
   maakt overlappende fetches (bv. na een gecrashte run) veilig om te
   herhalen.

`run_pipeline()` doet dit voor elk symbool/timeframe in de config, en laat
één mislukte combinatie de rest niet blokkeren (het resultaat-dict bevat
`None` voor een mislukte combinatie, met de fout in de logs).

## Rate limiting

CCXT's ingebouwde rate limiter regelt dit: exchanges worden aangemaakt met
`enableRateLimit: True` (`exchange.py::create_exchange`), waardoor elke
`fetch_ohlcv`-call automatisch wacht zolang de exchange's gedocumenteerde
limiet vereist. Bij het pagineren door jaren aan geschiedenis
(`fetch_ohlcv_since`) is er daarom bewust **geen** extra handmatige
`time.sleep` — dat zou of overbodig zijn, of juist uit de pas gaan lopen met
CCXT's eigen throttle.

## Scheduling (nu handmatig, later job-queue)

Voor deze fase is `scripts/run_pipeline.py` een simpel command-line script
dat je handmatig of via cron kan draaien:

```cron
*/5 * * * * cd /pad/naar/freqpanda_2.0 && .venv/bin/python scripts/run_pipeline.py config/pipeline.json
```

`run_pipeline()` zelf weet niets van hoe hij aangeroepen wordt — in fase 5
kan dezelfde functie net zo goed vanuit een job-queue-worker aangeroepen
worden zonder wijzigingen.

## Waarom een directe Postgres-connectie in plaats van de Supabase REST-client

Supabase biedt zowel een REST/PostgREST-client (`supabase-py`) als directe
Postgres-toegang. Voor deze fase is de workload bulk-upserts van
tijdreeksdata (honderden tot duizenden candles per fetch) en gefilterde
ranged reads — met rechtstreekse SQL (`psycopg2` + `execute_values` +
`ON CONFLICT`) is dat zowel eenvoudiger te doorgronden als veel efficiënter
dan per-rij REST-calls. Verbind met de standaard Postgres-connectionstring
die Supabase per project aanbiedt (Project Settings → Database).

## Configureren: symbolen/timeframes toevoegen

Alles staat in `config/pipeline.json` (of een eigen configbestand, zie
`load_pipeline_config`):

```json
{
  "exchange_id": "binance",
  "pairs": [
    { "symbol": "BTC/USDT", "timeframe": "1h" },
    { "symbol": "ETH/USDT", "timeframe": "1h" }
  ],
  "backfill_since": "2020-01-01T00:00:00Z"
}
```

Een nieuw symbool of timeframe toevoegen = een regel toevoegen aan `pairs`
en de pipeline opnieuw draaien; de eerste run backfillt vanaf
`backfill_since`, elke run daarna is incrementeel. Geen codewijziging nodig.

Voor een ander exchange: verander `exchange_id` naar een geldige
[CCXT exchange-id](https://github.com/ccxt/ccxt/wiki/exchange-markets) (bv.
`"kraken"`) — mits die exchange `fetch_ohlcv` ondersteunt.

## Tests

```bash
pytest tests/test_data_*.py -v
```

Alle CCXT- en database-calls zijn gemockt (`FakeExchange` voor CCXT-paginering,
`unittest.mock` voor psycopg2) — er wordt nooit een echte exchange-API of
database aangeroepen. `test_data_integration.py` bewijst dat de DataFrame die
`fetch_ohlcv_dataframe` teruggeeft ook echt door `freqpanda_strategy.run_strategy`
geaccepteerd wordt, tegen dezelfde synthetische data als de fase-1 tests.
