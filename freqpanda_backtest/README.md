# freqpanda_backtest — fase 3: backtest-engine

Zet de ruwe trade-lijst uit de fase-1 interpreter (`freqpanda_strategy.run_strategy`)
om in een equity-curve en prestatie-metrics, inclusief fees/slippage en
walk-forward-validatie. Neemt als input een `StrategyDefinition` en een OHLCV
DataFrame in het fase-2-formaat (`freqpanda_data.fetch_ohlcv_dataframe`).

Los van database-opslag (fase 5), optimalisatie/hyperopt (fase 4), UI en API.

## Snel starten

```python
from freqpanda_backtest import backtest
from freqpanda_strategy import load_strategy_definition
import pandas as pd

definition = load_strategy_definition("examples/ema_crossover.json")
df = pd.read_csv("btc_1h.csv", index_col="timestamp", parse_dates=True)  # of via freqpanda_data

result = backtest(definition, df, initial_capital=10_000.0, fee_pct=0.001, slippage_pct=0.0005)

print(result.metrics_dict())
```

## Architectuur

```
freqpanda_backtest/
  costs.py        TradingCosts: fee/slippage-model per fill
  equity.py        apply_costs_to_trades() + build_equity_curve()
  metrics.py        drawdown, Sharpe/Sortino, trade-stats — allemaal vectorized
  result.py        BacktestResult + serialisatie (metrics_dict/trade_records/equity_curve_records)
  backtest.py        backtest(): orkestreert het bovenstaande
  walkforward.py        train/test-window-splitsing + uitvoering
  batch.py        run_backtests_parallel(): veel varianten over CPU-cores
```

## Van trades naar equity: het kapitaal-model

Fase 1's interpreter is long-only en houdt maximaal één open positie
tegelijk aan (trades overlappen nooit). Er is geen aparte
position-sizing-regel in het schema, dus fase 3 maakt een expliciete keuze:
**elke trade zet het volledige beschikbare kapitaal in** en zet dat bij exit
weer volledig om in cash voordat de volgende trade kan openen (dus winst en
verlies componeren over trades heen — dit is de standaardaanname bij
afwezigheid van een expliciete sizing-regel, en makkelijk te vervangen zodra
er wel een is).

Per trade (kapitaal `E` vóór de trade):

```
entry_fill = entry_price * (1 + slippage_pct)
exit_fill  = exit_price  * (1 - slippage_pct)

quantity   = E * (1 - fee_pct) / entry_fill      # fee betaald op de aankoop-notional
proceeds   = quantity * exit_fill
E_next     = proceeds * (1 - fee_pct)            # fee betaald op de verkoop-opbrengst
```

Fee en slippage worden dus **per fill** toegepast (entry én exit apart), wat
overeenkomt met hoe een exchange het echt afhandelt: taker fee op elke order,
en slippage die je bij het kopen meer laat betalen en bij het verkopen minder
laat ontvangen.

## De equity-curve: mark-to-market, niet alleen bij exit

Een curve die alleen bij elke trade-exit een sprong maakt, verbergt
drawdowns die tijdens een open positie ontstaan (bijv. een strategie die
eerst flink onder water gaat voordat hij zijn take-profit raakt). Daarom
bouwt `build_equity_curve()` een waarde per candle:

- **buiten een positie**: vlak (cash staat stil, geen rendement)
- **op de entry-candle**: `quantity * entry_fill_price` — de papierwaarde
  direct na het betalen van de entry-fee, vóór enige prijsbeweging
- **tussen entry en exit** (exclusief beide): `quantity * close` — marked-to-market
  tegen de slotkoers van elke candle
- **op de exit-candle**: de daadwerkelijk gerealiseerde `E_next` — dit kan
  afwijken van `quantity * close` omdat een exit via stop-loss/take-profit/
  trailing-stop tegen een berekend niveau afgehandeld wordt, niet noodzakelijk
  tegen de slotkoers (zie fase 1's README voor die aanname)

Geïmplementeerd door direct in een numpy-array te schrijven per trade
(segment-gewijs), niet met een Python-loop per candle: kosten zijn
O(aantal candles + aantal trades), niet O(candles × trades).

## Metrics

Alles hieronder wordt met numpy/pandas-vectoroperaties op de (kleine)
trade-lijst of de equity-curve berekend — geen Python-loop over candles of
trades voor de aggregaties zelf.

- **Totaal rendement**: `final_capital/initial_capital - 1` (%) en
  `final_capital - initial_capital` (absoluut).
- **Sharpe ratio**: op basis van **per-candle** rendementen van de
  equity-curve (`equity.pct_change()`), niet per-trade-rendementen — zo
  tellen candles waarin je platliggend cash aanhoudt terecht mee als
  rendement 0 en drukken ze de volatiliteit, in plaats van onzichtbaar te
  zijn voor de berekening. Geannualiseerd met `sqrt(periods_per_year)`,
  waarbij `periods_per_year` wordt afgeleid uit de mediane tijd tussen twee
  candles in de input-DataFrame (dus geen aparte timeframe-parameter nodig).
  `risk_free_rate` (standaard 0, jaarlijkse fractie) wordt omgerekend naar
  een per-candle baseline.
- **Sortino ratio**: zelfde opzet, maar de noemer is de *downside deviation*:
  de RMS van `min(rendement - MAR, 0)` over **alle** periodes (niet alleen de
  verliezende), met MAR = de per-periode risk-free rate. Dit is de
  standaarddefinitie — een downside-deviation die alleen over de verliezende
  periodes middelt onderschat het risico systematisch.
- **Maximum drawdown**: `(equity - cummax(equity)) / cummax(equity)`, het
  minimum daarvan (als positieve fractie gerapporteerd). Duur = tijd tussen
  de piek vóór de top en het moment van herstel tot dat piekniveau (of tot
  het einde van de data als nooit hersteld — `recovery_time` is dan `None`).
- **Win-rate, aantal trades, gemiddelde winst/verlies**: per trade het
  netto (na fees/slippage) resultaat; winst = `net_pnl_abs > 0`, verlies =
  `net_pnl_abs < 0` (een trade die exact quitte speelt telt in geen van
  beide).
- **Profit factor**: `som(winst) / som(|verlies|)`. Oneindig als er winsten
  maar geen verliezen zijn, `NaN` als er helemaal geen trades zijn.

Alle ratio's geven `NaN` (nooit een exception) wanneer ze niet gedefinieerd
zijn — bijv. geen trades, of een volstrekt vlakke equity-curve zonder enige
variantie.

## Walk-forward validatie

`generate_walk_forward_windows()` knipt de tijdreeks in opeenvolgende,
niet-overlappende train/test-vensters (half-open intervallen: het candle op
exact de grens hoort bij het test-venster, niet bij beide):

```python
from freqpanda_backtest import generate_walk_forward_windows
import pandas as pd

windows = generate_walk_forward_windows(
    df.index,
    train_period=pd.Timedelta(days=180),
    test_period=pd.Timedelta(days=30),
)
```

Twee varianten:
- **rolling** (standaard, `anchored=False`): het train-venster schuift elke
  stap `step` (standaard = `test_period`) op, met vaste lengte
  `train_period` — "doorschuiven" zoals gevraagd.
- **anchored** (`anchored=True`): het train-venster begint altijd bij het
  begin van de dataset en groeit elke stap met `step` (expanding window) —
  handig als je juist wil zien hoe de strategie zich houdt naarmate er meer
  historie beschikbaar komt.

`run_walk_forward(definition, df, train_period, test_period, ...)` runt
vervolgens `backtest()` met **dezelfde, vaste** `definition` op zowel de
train- als de test-slice van elk venster, en geeft een lijst
`WalkForwardResult` terug (venster + beide `BacktestResult`s).

**Bewuste scope-grens**: fase 3 levert de venster-splitsing en
uitvoerings-harness. Het daadwerkelijke *optimaliseren* van
strategie-parameters per train-venster — het hele punt van walk-forward
validatie — is fase 4. Die schuift er tussenin:

```python
for window in generate_walk_forward_windows(df.index, train_period, test_period):
    train_df = df[(df.index >= window.train_start) & (df.index < window.train_end)]
    tuned_definition = optimize(definition, train_df)          # fase 4
    test_df = df[(df.index >= window.test_start) & (df.index < window.test_end)]
    result = backtest(tuned_definition, test_df, ...)
```

`run_walk_forward()` runt nu vast dezelfde definitie op train én test, wat
al bruikbaar is om te zien of train- en test-prestaties enigszins
samenhangen vóórdat er geoptimaliseerd wordt.

## Performance: waarom geen vectorbt, en wat wél gevectoriseerd is

`vectorbt` (of een vergelijkbare aanpak) zou de **signaalgeneratie** zelf
vectorized maken — d.w.z. de hele indicator- en conditie-evaluatie in één
keer over de hele DataFrame, in plaats van candle-voor-candle. Dat is precies
wat fase 1's interpreter *niet* doet, en met opzet: die loopt bewust
candle-voor-candle omdat dezelfde interpreter straks ongewijzigd voor live-executie
moet werken (candle-voor-candle is daar de enige optie), en fase 1's README
maakt dat een expliciete eis ("geen drift tussen backtest en live"). Signaalgeneratie
vectorized maken zou betekenen dat fase 3 zijn eigen, aparte
strategie-uitvoering herimplementeert — precies de drift die het hele project
wil vermijden.

Dus: fase 3 vectorizet wat **binnen zijn eigen scope** valt — de equity-curve
en alle metrics — met numpy/pandas-arrayoperaties (geen Python-loop over
candles of trades voor de aggregaties). De vraag is dan: hoeveel tijd
bespaart dat, gegeven dat `run_strategy()` zelf een candle-voor-candle
Python-loop blijft?

### Benchmark (`scripts/benchmark_backtest.py`, 1 jaar 1h-candles = 8760 candles)

```
run_strategy() only (interpreter):      mean 239.93 ms
backtest() end-to-end:                  mean 249.58 ms
=> fase 3's eigen werk voegt ~9.65 ms toe (~4%) bovenop de interpreter
=> ~4 runs/seconde, ~14.400 runs/uur, single-core, sequentieel
```

(Gemeten op deze omgeving; absolute getallen verschillen per machine, maar
de verhouding — interpreter domineert, fase 3's toevoeging is marginaal — is
het punt.)

Conclusie: verder micro-optimaliseren van de metrics-berekening heeft weinig
zin, want de interpreter-loop domineert de runtime toch al. De praktische
hefboom voor "duizenden varianten" is dus **parallellisatie over
CPU-cores**, niet nog vectoriseren binnen één run — `backtest()` is een pure
functie van `(definition, df, capital, fees)` zonder gedeelde state, dus
embarrassingly parallel.

### `run_backtests_parallel()`

```python
from freqpanda_backtest import run_backtests_parallel

results = run_backtests_parallel(variant_definitions, df, max_workers=8, fee_pct=0.001)
```

Verdeelt de varianten over een `ProcessPoolExecutor`. De DataFrame wordt
precies één keer per workerproces verzonden (via de pool-`initializer`), niet
per taak — bij duizenden varianten die dezelfde (mogelijk grote) DataFrame
delen scheelt dat aanzienlijk pickle-overhead.

### Benchmark (`scripts/benchmark_parallel.py`, 40 varianten, 4 cores)

```
sequentieel: 9.82s (245.6 ms/variant)
parallel:    2.86s (71.6 ms/variant)
speedup:     3.43x
```

Op deze 4-core-machine dus ruim 3× sneller, en dat schaalt verder met meer
cores. Voor fase 4 (hyperopt over honderden/duizenden varianten): reken op
zo'n `aantal_cores × 14.400` runs/uur als vuistregel, met deze specifieke
strategie/dataset-grootte.

## Fees en slippage: aanbevolen waardes

Geen ingebouwde default die "realistisch" claimt te zijn — dat hangt af van
de exchange en het orderbook. Als richtlijn: Binance spot taker fee is
0.1% (`fee_pct=0.001`); slippage is sterk marktafhankelijk maar 0.05%
(`slippage_pct=0.0005`) is een redelijk startpunt voor liquide paren als
BTC/USDT op de gangbare timeframes. `backtest()`'s default is
`fee_pct=0.001, slippage_pct=0.0`.

## Resultaat-object: klaar voor fase 5/6

`BacktestResult` is bewust plat en dataclass-gebaseerd (geen ORM- of
DataFrame-afhankelijkheden in de vorm zelf), met drie methodes die direct
bruikbaar zijn zodra fase 5 (Supabase) en fase 6 (dashboard) er zijn:

- `metrics_dict()` — één platte dict, één rij voor een `backtest_runs`-tabel.
- `trade_records()` — lijst van dicts, rijen voor een `backtest_trades`-tabel.
- `equity_curve_records()` — lijst van `{timestamp, equity}`-dicts, rijen
  voor een `backtest_equity`-tabel of direct input voor een grafiek.

Alle timestamps/timedelta's zijn in deze methodes al naar
JSON-serialiseerbare vormen (ISO-strings, seconden) omgezet.

## Tests

```bash
pytest tests/test_backtest*.py -v
```

- `test_backtest_equity.py` — kapitaal-compounding met de hand nagerekend
  (met en zonder fees), en de mark-to-market equity-curve-opbouw.
- `test_backtest_metrics.py` — drawdown, Sharpe/Sortino en trade-stats elk
  met een met de hand berekende verwachte uitkomst.
- `test_backtest.py` — `backtest()` end-to-end op triviale, met de hand na
  te rekenen strategieën (directe OHLCV-vergelijkingen, geen indicators).
- `test_backtest_walkforward.py` — venstergeneratie (rolling/anchored,
  geen overlap) en een end-to-end walk-forward-run op synthetische data.
- `test_backtest_batch.py` — `run_backtests_parallel()` geeft resultaten in
  dezelfde volgorde als de input terug.

## Benchmarks zelf draaien

```bash
python scripts/benchmark_backtest.py    # één run: interpreter vs. fase-3-overhead
python scripts/benchmark_parallel.py    # sequentieel vs. parallel over meerdere varianten
```
