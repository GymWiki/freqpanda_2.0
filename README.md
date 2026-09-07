# freqpanda

Eigen crypto trading bot platform, gebouwd in fases:

- **Fase 1 — strategie-schema + interpreter** (`freqpanda_strategy/`, hieronder):
  strategie-definitie als data, en een strategie-agnostische interpreter die
  die definitie + een OHLCV DataFrame omzet in een lijst van trades.
- **Fase 2 — data-pipeline** (`freqpanda_data/`, zie
  [freqpanda_data/README.md](freqpanda_data/README.md)): haalt OHLCV-data op
  via CCXT, slaat het incrementeel op in Supabase/Postgres, en levert het
  terug als DataFrame in exact het formaat dat fase 1 verwacht.
- **Fase 3 — backtest-engine** (`freqpanda_backtest/`, zie
  [freqpanda_backtest/README.md](freqpanda_backtest/README.md)): zet de
  trades uit fase 1 om in een equity-curve en prestatie-metrics (Sharpe,
  Sortino, drawdown, profit factor, ...), inclusief fees/slippage en
  walk-forward-validatie.
- **Fase 4 — optimalisatie & strategie-generatie** (`freqpanda_optimize/`,
  zie [freqpanda_optimize/README.md](freqpanda_optimize/README.md)):
  optimaliseert indicator-parameters met Optuna (gevalideerd met
  walk-forward, niet één train/test-split), genereert willekeurige nieuwe
  strategie-varianten binnen opgegeven grenzen, en beoordeelt ze in batch.
- **Fase 5 — backend API & job-queue** (`freqpanda_api/`, zie
  [freqpanda_api/README.md](freqpanda_api/README.md)): FastAPI-backend met
  strategie-CRUD, asynchrone backtest-/optimalisatie-jobs via een
  Redis/RQ-wachtrij, resultaten in Supabase, en API-key-auth — draait via
  `docker compose up` (API + worker + Redis).

Nog los van UI en live-executie — dat komt in latere fases, bovenop
dezelfde interpreter.

## Installeren

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Fase 1: strategie-schema + interpreter

## Snel starten

```python
from freqpanda_strategy import load_strategy_definition, run_strategy
import pandas as pd

definition = load_strategy_definition("examples/ema_crossover.json")

df = pd.read_csv("mijn_ohlcv.csv", index_col="timestamp", parse_dates=True)
# df moet kolommen open, high, low, close, volume hebben, oplopend gesorteerd op tijd

trades = run_strategy(definition, df)
for t in trades:
    print(t.entry_time, t.entry_price, "->", t.exit_time, t.exit_price, t.exit_reason)
```

## Architectuur

```
freqpanda_strategy/
  schema.py       Pydantic-modellen: StrategyDefinition, IndicatorConfig,
                   ParamRange, Comparison, Logical, RiskManagement
  indicators.py   Registry van indicator-naam -> berekeningsfunctie (ta-lib)
  conditions.py   Evalueert een conditie-boom tot een boolean pandas Series
  validation.py   Semantische checks die de indicator-registry nodig hebben
  interpreter.py  run_strategy(): indicators berekenen, condities evalueren,
                   candle-voor-candle trades genereren
  loader.py       JSON/YAML bestand -> StrategyDefinition
```

De interpreter kent **geen enkele specifieke strategie**. Hij weet alleen
hoe hij het schema moet lezen: welke indicators bestaan (via de registry),
en hoe een conditie-boom (vergelijkingen + and/or/not) evalueert tot een
boolean signaal per candle. Een nieuwe strategie toevoegen betekent alleen
een nieuw JSON/YAML-bestand schrijven — geen Python-code.

## Het schema

### Indicators

```json
{
  "name": "rsi",
  "alias": "rsi14",
  "params": { "period": { "default": 14, "min": 7, "max": 21, "step": 1 } }
}
```

- `name` selecteert de implementatie uit de registry (`rsi`, `ema`, `sma`,
  `macd`, `bbands`).
- `alias` is de unieke naam waarmee condities naar de output van deze
  indicator verwijzen. Voor indicators met één output (RSI, EMA, SMA) is dat
  gewoon de alias zelf als kolomnaam. Voor indicators met meerdere outputs
  (MACD, Bollinger Bands) worden kolommen `f"{alias}_{sub_naam}"`, bv.
  `macd1_macd`, `macd1_signal`, `macd1_hist` of `bb_upper`, `bb_middle`,
  `bb_lower`.
- Elke parameter is óf een vast getal (`"period": 14`) óf een `ParamRange`
  (`{"default": ..., "min": ..., "max": ..., "step": ...}`). De interpreter
  gebruikt altijd `default`; `min`/`max`/`step` zijn er voor een latere
  hyperopt-fase die dezelfde schema's kan herlezen zonder dat het formaat
  hoeft te veranderen.

Nieuwe indicator toevoegen: schrijf een `_compute`- en `_outputs`-functie in
`indicators.py` en registreer ze in `INDICATOR_REGISTRY`. De rest van de
package (schema, conditions, interpreter) hoeft niet aangepast te worden.

### Condities (DSL)

Een conditie is een boom van twee node-types, onderscheiden door `"type"`:

**`comparison`** — een blad-conditie:
```json
{ "type": "comparison", "left": "rsi14", "op": "lt", "right": 30 }
```
`left`/`right` zijn ofwel een getal (constante), ofwel een string die
verwijst naar een OHLCV-kolom (`open`, `high`, `low`, `close`, `volume`) of
een indicator-outputkolom. Beschikbare operators: `gt`, `gte`, `lt`, `lte`,
`eq`, `ne`, `crosses_above`, `crosses_below` (de laatste twee vergelijken de
huidige candle met de vorige, voor kruisingen zoals een EMA-crossover).

**`logical`** — combineert geneste condities:
```json
{
  "type": "logical",
  "op": "and",
  "conditions": [ { ... }, { ... } ]
}
```
`op` is `and`/`or` (minimaal 2 geneste condities) of `not` (precies 1).

Condities kunnen willekeurig diep genest worden, zie
`examples/rsi_mean_reversion.json` voor een `and` van twee vergelijkingen.

### Risk management (verplicht)

```json
{ "stop_loss_pct": 0.02, "take_profit_pct": 0.06, "trailing_stop_pct": 0.03 }
```

`risk_management` is een verplicht onderdeel van elke strategie-definitie,
losstaand van de indicator-condities. `stop_loss_pct` en `take_profit_pct`
zijn beide verplicht (fracties, dus `0.02` = 2%) zodat een strategie nooit
per ongeluk zonder basale risicobeheersing gedefinieerd kan worden.
`trailing_stop_pct` is optioneel, omdat niet elke strategie een trailing
stop nodig heeft.

## Validatie

Twee lagen:

1. **Structureel** (Pydantic, in `schema.py`): verplichte velden,
   type-checks, numerieke bounds (bv. `min <= default <= max`,
   `0 < stop_loss_pct < 1`), arity van `and`/`or`/`not`, unieke
   indicator-aliassen. Een ongeldige definitie geeft een `ValidationError`
   met per veld een duidelijke foutmelding.
2. **Semantisch** (`validation.py`, gebruikt door `run_strategy` vóór elke
   run): kent de indicator-registry en checkt dingen die Pydantic niet kan
   weten zonder die registry — onbekende indicator-namen, onbekende
   parameter-namen per indicator, en condities die verwijzen naar een
   kolom die geen enkele indicator produceert. Faalt dit, dan gooit
   `run_strategy` een `StrategyValidationError` met alle gevonden problemen
   in één keer (niet alleen de eerste).

## Interpreter: aannames

Deze zijn expliciete keuzes voor fase 1, gedocumenteerd zodat je ze kan
beoordelen (en later kan aanpassen zonder het schema te breken):

- **Alleen long.** Er is geen `direction`-veld; short-strategieën zijn een
  latere uitbreiding (een `direction: short` veld zou eenvoudig aan het
  schema toe te voegen zijn zonder de rest te breken).
- **Geen lookahead.** Entry/exit-signalen op een candle gebruiken alleen de
  eigen OHLCV van die candle (candle wordt behandeld als afgesloten op het
  moment van evalueren) en worden uitgevoerd tegen de **close** van diezelfde
  candle.
- **Stop-loss/take-profit tegen intrabar high/low.** Omdat er geen tick-data
  is, wordt aangenomen dat een candle zijn stop-loss geraakt heeft als de
  **low** onder het niveau komt, en zijn take-profit als de **high** erboven
  komt — het gebruikelijke worst-case/best-case-aanname bij alleen OHLCV.
- **Prioriteit bij meerdere triggers op dezelfde candle:**
  `stop_loss` > `take_profit` > `trailing_stop` > `exit_signal`
  (risicobeheersing gaat altijd voor een indicator-exit).
  Als je verwacht dat een candle nooit én de stop én de TP raakt op je eigen
  timeframe, verandert dit niets aan het resultaat.
- **Open posities aan het einde van de data worden niet geforceerd
  gesloten.** Ze verschijnen niet in de teruggegeven trade-lijst, omdat er
  geen echte exit-prijs is om te rapporteren.
- **Dezelfde interpreter voor backtest en live** (het uiteindelijke doel):
  `run_strategy` doet zijn werk puur op basis van het schema en een
  DataFrame, zonder state die alleen bij "een hele DataFrame in één keer
  verwerken" hoort. Voor live executie kan dezelfde `compute_indicators` +
  `evaluate_condition` combinatie candle-voor-candle op een groeiende
  DataFrame toegepast worden, mits de nieuwste candle pas wordt toegevoegd
  zodra hij is afgesloten (anders ontstaat alsnog lookahead-drift tussen
  backtest en live — dat valt buiten deze fase, maar de interpreter zelf
  legt hier geen aannames op die dit onmogelijk zouden maken).

## Waarom `ta` in plaats van `pandas-ta`

`pandas-ta` heeft op dit moment bekende compatibiliteitsproblemen met
recente numpy-versies (het importeert `numpy.NaN`, dat in numpy >= 2.0 is
verwijderd). `ta` is een kleinere, actief werkende library, puur op
pandas/numpy gebaseerd, en dekt RSI, EMA, SMA, MACD en Bollinger Bands
volledig — genoeg voor deze fase, met minder risico op dependency-gedoe.

## Voorbeeldstrategieën

- `examples/ema_crossover.json` — long bij een bullish EMA-crossover
  (fast crosses_above slow), exit bij de omgekeerde cross of risk-limieten,
  inclusief trailing stop.
- `examples/rsi_mean_reversion.json` — long wanneer RSI oversold is **en**
  de prijs de onderste Bollinger Band raakt (voorbeeld van een `and`-combinatie
  van twee indicators), exit wanneer RSI overbought raakt.

Beide worden in `tests/test_interpreter.py` tegen synthetische data
gedraaid (een deterministische sinusprijs met kleine ruis, zie
`tests/conftest.py`) en produceren aantoonbaar trades.

## Uitbreiden

- **Nieuwe indicator**: compute/outputs-functie in `indicators.py` +
  registreren in `INDICATOR_REGISTRY`.
- **Nieuwe vergelijkingsoperator**: `_apply_op` in `conditions.py`.
- **Nieuw risicomechanisme** (bv. break-even stop): veld toevoegen aan
  `RiskManagement` in `schema.py` en de bijbehorende check in de
  exit-volgorde in `interpreter.py::run_strategy`.
- **Short-strategieën / meerdere posities tegelijk**: huidige interpreter
  houdt bewust maar één open positie per run bij (eenvoudig, voorspelbaar
  gedrag als basis); dat is de plek om uit te breiden zodra dat nodig is.

## Tests

```bash
pytest -v
```

Dekt: schema-validatie (geldig/ongeldig), elke indicator-berekening,
elke vergelijkings-/logische operator, de interpreter (entry/exit,
stop-loss/take-profit/trailing-stop en hun prioriteit, geen lookahead, open
posities aan het eind), semantische validatie-foutmeldingen, en de twee
voorbeeldstrategieën end-to-end tegen synthetische data.
