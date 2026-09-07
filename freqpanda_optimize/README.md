# freqpanda_optimize — fase 4: optimalisatie en strategie-generatie

Twee dingen: **(a)** parameters van een bestaande fase-1 strategie-definitie
optimaliseren met [Optuna](https://optuna.org/), gevalideerd met de
walk-forward-opzet uit fase 3 (niet één enkele train/test-split), en **(b)**
willekeurig nieuwe strategie-varianten genereren binnen door jou opgegeven
grenzen, en die in batch beoordelen.

Los van database-opslag (fase 5), UI en live trading.

## Snel starten

```bash
python scripts/optimize_example.py
```

```python
from freqpanda_optimize import optimize, refit_on_full_history
from freqpanda_strategy import load_strategy_definition
import pandas as pd

definition = load_strategy_definition("examples/ema_crossover.json")

result = optimize(
    definition, df,
    train_period=pd.Timedelta(days=60), test_period=pd.Timedelta(days=20),
    metric="sharpe_ratio", n_trials=25,
    backtest_kwargs={"fee_pct": 0.001, "slippage_pct": 0.0005},
)
print(result.summary())  # in-sample vs out-of-sample per venster

final = refit_on_full_history(definition, df, metric="sharpe_ratio", n_trials=25)
# final.best_definition -> de strategie-definitie om te deployen
```

## Architectuur

```
freqpanda_optimize/
  search_space.py    ParamRange -> Optuna search space, en terug naar een concrete StrategyDefinition
  scoring.py          BacktestResult -> één getal om te maximaliseren
  optimize.py          optimize_single_split / optimize (walk-forward) / refit_on_full_history
  generate.py          generate_variants(): willekeurige strategie-varianten binnen grenzen
  evaluate.py          evaluate_variants(): N varianten in batch draaien, gesorteerd op metric
```

## Van `ParamRange` naar Optuna en terug

Fase 1's schema staat `ParamRange` (een default + min/max/step) alleen toe
op **indicator-parameters** (`IndicatorConfig.params`) — `RiskManagement`'s
velden zijn platte getallen, geen `ParamValue`. Fase 4 optimaliseert dus
indicator-parameters; risk-parameters optimaliseerbaar maken zou een
schema-wijziging in fase 1 zijn, geen toevoeging hier.

`build_search_space(definition)` verzamelt elke `ParamRange` als een
`ParamSpec`, geadresseerd als `"{alias}.{param_naam}"` (bv.
`"ema_fast.period"`). `suggest_params(trial, search_space)` vraagt Optuna om
één waarde per spec — `suggest_int` wanneer min/max/step/default allemaal
hele getallen zijn (een periode-achtige parameter), anders `suggest_float`.
`materialize_definition(definition, values)` bouwt een kopie van de
definitie met die specifieke parameters vervangen door een vast getal —
niet-meegegeven parameters (inclusief andere `ParamRange`s) blijven
onaangeroerd, en `run_strategy` valt daar automatisch terug op `.default`.

## Optimalisatie: drie lagen

1. **`optimize_single_split(definition, train_df, test_df, ...)`** — één
   Optuna-study op `train_df`, dan één keer de beste trial evalueren op
   `test_df` (nooit gezien tijdens de zoektocht). Dit is de bouwsteen; op
   zichzelf is dit exact de "enkele train/test-split" die de opdracht
   expliciet niet als enige aanpak wil.
2. **`optimize(definition, df, train_period, test_period, ...)`** — het
   hoofd-entrypoint. Knipt `df` met fase 3's `generate_walk_forward_windows`
   in opeenvolgende vensters en roept `optimize_single_split` onafhankelijk
   aan op elk venster. Geeft een `OptimizationResult` terug met per venster
   zowel de in-sample (train) als out-of-sample (test) score.
3. **`refit_on_full_history(definition, df, ...)`** — nadat `optimize()`
   heeft laten zien dat de aanpak niet toevallig op één periode overfit,
   één laatste Optuna-study over **alle** beschikbare data, voor de
   parameter-set die je daadwerkelijk gaat draaien. Hier is geen
   held-out test-set meer (er is geen ongeziene data meer over) — dit is een
   *deployment*-stap, geen validatie-stap, en het resultaat is per
   definitie in-sample. Lees het nooit als bewijs dat de strategie werkt;
   dat bewijs (of het ontbreken ervan) staat in `optimize()`'s
   out-of-sample-kolom.

`n_trials`/`timeout` gaan naar `optuna.Study.optimize()`, dat gegarandeerd
terugkeert zodra één van beide bereikt is — belangrijk zodra dit vanuit een
fase-5 job-queue gedraaid wordt en niet oneindig mag lopen. Bij
`optimize()` (walk-forward) gelden ze **per venster**, dus het totale
budget is ruwweg `aantal_vensters × n_trials`.

## Hoe overfitting wordt tegengegaan

Drie dingen, samen:

1. **Walk-forward in plaats van één split.** `optimize()` optimaliseert en
   evalueert onafhankelijk op meerdere opeenvolgende vensters. Eén venster
   waar de geoptimaliseerde parameters toevallig goed op scoren, zegt
   weinig; **consistent** een kleine in-sample/out-of-sample-kloof over
   meerdere vensters zegt veel meer.
2. **Expliciete in-sample vs. out-of-sample rapportage.**
   `OptimizationResult.summary()` geeft een tabel met per venster beide
   scores; `mean_in_sample_score()` / `mean_out_of_sample_score()` geven het
   gemiddelde. Het verschil (`in - out`) is je overfitting-signaal: dicht
   bij 0 is goed, een grote, consistente kloof betekent dat de zoektocht
   ruis in de train-data leert in plaats van een echt patroon.
3. **Nooit de test-set gebruiken om te kiezen.** Binnen één venster ziet de
   Optuna-study alleen `train_df` — `test_df` wordt precies één keer
   aangeraakt, ná afloop van de zoektocht, puur om te rapporteren. Er is
   geen pad waarlangs de test-score de zoektocht kan beïnvloeden.

Wat dit **niet** doet: het kiest niet automatisch "de beste" strategie of
"de beste" parameter-set voor je. Dat is een menselijke beoordeling op basis
van de gerapporteerde in-sample/out-of-sample-tabel — precies waarom
`summary()` een leesbare tabel teruggeeft in plaats van alleen een enkel
"score"-getal.

## Strategie-generatie: een eenvoudig startpunt

`generate_variants(bounds, n)` genereert `n` willekeurige
strategie-definities, elk volgens één van twee templates (gekozen door een
munt op te gooien) die precies de twee fase-1-voorbeeldstrategieën
spiegelen:

- **crossover**: twee indicators van een "moving-average-achtig" type
  (rechtstreeks vergelijkbare output, bv. twee EMA's, of EMA vs SMA),
  entry op `a crosses_above b`, exit op `a crosses_below b`.
- **threshold**: één "oscillator-achtige" indicator (begrensd bereik, bv.
  RSI), entry als hij onder een lage drempel zakt, exit als hij boven een
  hoge drempel komt — een mean-reversion-vorm.

```python
from freqpanda_optimize import GenerationBounds, IndicatorBounds, generate_variants

bounds = GenerationBounds(
    crossover_indicators=[
        IndicatorBounds(name="ema", param_ranges={"period": (5, 50, 1)}),
        IndicatorBounds(name="sma", param_ranges={"period": (5, 50, 1)}),
    ],
    threshold_indicators=[
        IndicatorBounds(name="rsi", param_ranges={"period": (7, 21, 1)}, threshold_range=(20.0, 80.0)),
    ],
    stop_loss_pct_range=(0.01, 0.05),
    take_profit_pct_range=(0.02, 0.10),
)
variants = generate_variants(bounds, n=100)
```

Elke gegenereerde indicator-parameter blijft een `ParamRange` (geen vast
getal) — een variant is dus direct te backtesten zoals hij is (fase 1's
interpreter valt terug op `.default`), én direct door te geven aan
`optimize()` om verder te verfijnen.

### Waarom dit bewust eenvoudig is, en hoe uit te breiden

Dit is letterlijk toeval binnen grenzen — geen leren van wat werkt, geen
sturing richting veelbelovende regio's van de zoekruimte. Dat is prima als
startpunt (en goedkoop: genereren kost niets, alle "intelligentie" zit in de
batch-evaluatie erna), maar het is de plek om later gerichter te worden:

- **Fitness-gestuurd doorfokken**: de best presterende varianten uit
  `evaluate_variants()` als basis nemen voor de volgende generatie
  (parameter-ranges rond hun waarden vernauwen, of onderdelen
  combineren — een eenvoudig genetisch algoritme). `optimize()` past hier
  direct in: een veelbelovende variant eerst optimaliseren voordat je hem
  meeneemt naar de volgende generatie.
- **Grammatica-/sjabloon-uitbreiding**: meer templates naast crossover/
  threshold (bv. een MACD-histogram-cross, of een combinatie van drie
  condities met `and`/`or`) — `generate.py`'s twee `_generate_*_variant`-
  functies zijn het enige dat hoeft te groeien; het publieke
  `generate_variants`-contract blijft gelijk.
- **LLM- of regel-gestuurde generatie**: een taalmodel (of een
  domeinspecifieke regelset) laten voorstellen welke indicator-combinaties
  economisch zinnig zijn, in plaats van uniform willekeurig te kiezen —
  dit zou een nieuwe `generate_*` -functie zijn die dezelfde
  `StrategyDefinition`-vorm teruggeeft, dus verder niets in `evaluate.py`
  of `optimize.py` hoeft te veranderen.

## Batch-evaluatie

```python
from freqpanda_optimize import evaluate_variants

ranked = evaluate_variants(variants, df, metric="sharpe_ratio", max_workers=8, fee_pct=0.001)
best_definition, best_result = ranked[0]
```

Hergebruikt fase 3's `run_backtests_parallel` rechtstreeks (verspreid over
een process-pool) en sorteert de `(definitie, resultaat)`-paren aflopend op
`metric`. Een variant met een ongedefinieerde metric (bv. 0 trades, dus een
NaN Sharpe) krijgt via `score_from_result` de slechtst mogelijke score en
zakt naar onderen, in plaats van de sortering te breken met een rauwe
NaN-vergelijking.

## `metric`: naam of eigen functie

Overal waar `metric` voorkomt (`optimize()`, `evaluate_variants()`, ...) mag
dat een string zijn die overeenkomt met een veld op `BacktestResult`
(`"sharpe_ratio"`, `"sortino_ratio"`, `"total_return_pct"`,
`"profit_factor"`, ...), of een eigen samengestelde functie:

```python
def composite(result):
    return result.sharpe_ratio - 0.5 * result.max_drawdown_pct

result = optimize(definition, df, train_period=..., test_period=..., metric=composite)
```

## Voorbeeld-run

`scripts/optimize_example.py` optimaliseert `examples/ema_crossover.json`
(uit fase 1) over ~200 dagen synthetische 1h-data met een langzame
regime-drift erin (zodat vensters elkaar niet triviaal nabootsen), met
walk-forward-vensters van 60 dagen train / 20 dagen test. Echte output van
een run:

```
train_start  train_end test_start   test_end  in_sample_score  out_of_sample_score  num_trades_test
 2023-01-01 2023-03-02 2023-03-02 2023-03-22        28.804519            27.662114                7
 2023-01-21 2023-03-22 2023-03-22 2023-04-11        28.781412            27.572481                7
 2023-02-10 2023-04-11 2023-04-11 2023-05-01        29.043985            27.250700                7
 2023-03-02 2023-05-01 2023-05-01 2023-05-21        28.769087            24.492686                7
 2023-03-22 2023-05-21 2023-05-21 2023-06-10        28.668938            24.165650                7
 2023-04-11 2023-06-10 2023-06-10 2023-06-30        28.357470            27.780602                7

Mean in-sample Sharpe:     28.738
Mean out-of-sample Sharpe: 26.487
Degradation (in - out):    2.250
```

(Deze Sharpe-waarden zijn torenhoog omdat de synthetische testdata een
regelmatige sinusgolf is met een vaste periode van 60 candles — precies wat
een EMA-crossover kan exploiteren. Op echte marktdata verwacht je Sharpe's
in de orde van 1-3, niet 28; het punt van dit voorbeeld is de
in-sample/out-of-sample-vergelijking, niet het absolute getal.) De kloof
tussen in-sample en out-of-sample is hier klein en consistent (~2 punten op
~28) — een teken dat de optimalisatie een écht patroon in de data vindt in
plaats van ruis, in elk geval voor deze (sterk regelmatige) synthetische
reeks.

## Tests

```bash
pytest tests/test_optimize*.py -v
```

- `test_optimize_search_space.py` — `ParamRange` → Optuna-suggesties (int
  vs. float), en dat `materialize_definition` de originele definitie niet
  muteert en het resultaat direct door `run_strategy` heen kan.
- `test_optimize_scoring.py` — metric-by-name, custom callables, en dat NaN
  altijd de slechtste score oplevert.
- `test_optimize_generate.py` — gegenereerde varianten volgen hun template,
  zijn deterministisch met een geseede RNG, en overleven zowel fase 1's
  Pydantic-validatie als de semantische validatie.
- `test_optimize.py` — `optimize_single_split`, `optimize` (walk-forward)
  en `refit_on_full_history` end-to-end op synthetische data, met een klein
  `n_trials`-budget voor snelheid.
- `test_optimize_evaluate.py` — sorteervolgorde, inclusief dat een
  NaN-metric (0 trades) altijd onderaan eindigt.
