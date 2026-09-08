# freqpanda_execution — fase 7: live en paper trading-executie

Voert een fase-1 strategiedefinitie daadwerkelijk uit tegen realtime
marktdata: paper (gesimuleerde fills tegen een virtuele portfolio) of live
(echte orders via CCXT). Gebruikt de fase-1-interpreter ongewijzigd voor
alle indicator-/conditielogica, zodat er geen verschil kan ontstaan tussen
wat de backtester (fase 3) simuleerde en wat een live bot doet — zie "Geen
drift tussen backtest en live" hieronder voor het bewijs daarvan.

Rapporteert status, positie en trades naar dezelfde Postgres/Supabase-
database als fase 5 (`bots`, `bot_state`, `bot_trades`, `bot_events` —
migratie `migrations/0003_create_execution_tables.sql`), zodat de
fase-6-webapp dit kan tonen via de nieuwe `freqpanda_api`-router
(`/api/v1/bots/...`, zie `freqpanda_api/routers/bots.py`).

## Architectuur

```
freqpanda_execution/
  crypto.py             Fernet-encryptie voor exchange-API-keys (rest)
  config.py              Settings uit env vars (poll-intervallen, crash-loop-protectie)
  ids.py                  Prefixed id's (cred_..., bot_..., bottrade_...)
  repository.py           DB-laag: credentials, bots, bot_state, bot_trades, bot_events
  risk.py                 RiskMiddleware: hard stop-loss, drawdown-circuit breaker, order-sanity-checks
  live_interpreter.py     Live tegenhanger van freqpanda_strategy.run_strategy — zelfde indicator-/conditielogica, andere bookkeeping-loop
  broker.py               Fill-simulatie (paper) of echte orders (live), beide achter dezelfde Broker-interface
  feed.py                 Realtime OHLCV: websocket (ccxt.pro) met polling-fallback, roept per candle-close terug
  bot.py                  Bot: knoopt feed + live_interpreter + risk + broker + repository aan elkaar
  runner.py               Procesentrypoint: `python -m freqpanda_execution.runner <bot_id>`
  supervisor.py           Reconciliatie-loop: start/stopt één subprocess per bot o.b.v. bots.desired_status
```

Elke laag heeft precies één taak en importeert niets uit de laag erboven —
`bot.py` is de enige plek die alle andere modules kent.

### Eén bot = één proces

Een "bot" is (strategie + symbool + timeframe + exchange-account + mode).
Elke bot draait als eigen OS-proces (`python -m freqpanda_execution.runner
<bot_id>`), gestart en bewaakt door `supervisor.py`. Dat proces-per-bot-
ontwerp is een expliciete keuze:

- **RQ (fase 5's jobqueue) is hier het verkeerde gereedschap** — RQ is
  gebouwd voor kortlopende, eindige taken (een backtest, een optimalisatie);
  een bot draait juist oneindig door.
- **Losse containers per bot** zou nog beter isoleren, maar is voor een
  MVP op één VPS onnodige operationele overhead (image-builds, orchestratie)
  voor wat `subprocess.Popen` al oplevert: als bot A een onverwerkte
  exception gooit of vastloopt, blijft bot B — en de API — gewoon draaien.
  Het enige dat bots met elkaar delen is de Postgres-database.

`supervisor.py` doet niets anders dan **reconciliatie**, naar het patroon
van een Kubernetes-controller: gewenste staat leeft in de database
(`bots.desired_status`, `'running'` of `'stopped'`), werkelijke staat is
"is er een levend subprocess voor deze bot_id", en de enige taak van de
loop is die twee gelijk te trekken — elke `SUPERVISOR_POLL_INTERVAL_SECONDS`
seconden, voor altijd, zonder ooit te hoeven weten *waarom* de gewenste
staat veranderde (een API-call vanuit de webapp is voldoende).

Crasht een bot-proces onverwacht terwijl het nog gewenst 'running' is, dan
herstart de supervisor het automatisch — met **crash-loop-bescherming**:
na `MAX_RESTARTS_IN_WINDOW` crashes binnen `CRASH_LOOP_WINDOW_SECONDS`
geeft de supervisor het op, zet de bot op status `'error'`, en herstart
pas weer nadat `desired_status` handmatig uit en weer aan is gezet (via de
API) — dit voorkomt dat een bot met een structurele bug de exchange blijft
bestoken met foutieve requests.

### Geen drift tussen backtest en live

`freqpanda_strategy.run_strategy` (fase 1/3) loopt in één keer over een
complete historische DataFrame en geeft alleen *afgeronde* trades terug —
een positie die aan het eind van de data nog open staat, wordt bewust nooit
teruggegeven. Live executie heeft het tegenovergestelde nodig: weten zodra
een positie opengaat, zodat er nu een order geplaatst kan worden — niet
achteraf, zodra toevallig ook een bijpassende exit in een latere aanroep
verschijnt.

`live_interpreter.py` lost dit op door fase 1's eigen
`compute_indicators`/`evaluate_condition` **ongewijzigd** te hergebruiken —
dat is letterlijk dezelfde code die de backtester gebruikt. Alleen de
bookkeeping-loop (welke candle → welke statusovergang) is opnieuw
geschreven, met exact dezelfde prioriteitsvolgorde (stop_loss >
take_profit > trailing_stop > exit_signal) en exact dezelfde "alleen
instappen als er geen positie open is"-regel als `run_strategy`.

`tests/test_live_interpreter.py` is het daadwerkelijke bewijs hiervan, geen
losse claim in een docstring: dezelfde OHLCV-data wordt zowel in één keer
door `run_strategy()` gehaald als candle-voor-candle door
`LivePositionTracker`, en de resulterende tradelijsten moeten exact gelijk
zijn — over meerdere random seeds en twee verschillende strategievormen
(met en zonder indicatoren/exit-condities).

### Risk-middleware (`risk.py`)

Drie onafhankelijke veiligheidslagen, die nooit uitgaan van "de interpreter
heeft het toch al goed"::

1. **Hard stop-loss** (`check_hard_stop_loss`) — herleidt het stop-loss-
   niveau uit `risk_management.stop_loss_pct` en checkt dat tegen élke
   prijsupdate die de feed ziet, niet alleen bij candle-close. De
   interpreter handhaaft dezelfde stop-loss al, maar alleen op het moment
   dat hij een gesloten candle evalueert; dit is een tweede, onafhankelijke
   check op tick-niveau, zodat een trage candle (illiquide paar, lange
   timeframe) of een bug in de live-trackingloop een positie niet voorbij
   zijn stop kan laten lopen. Triggert dit, dan wordt er een apart
   `hard_stop_loss`-event gelogd (naast het normale `exit`-event) zodat
   zichtbaar blijft dát deze onafhankelijke laag ingreep, en niet alleen
   dat de positie sloot.
2. **Max-drawdown circuit breaker** (`update_equity`) — stopt de bot
   volledig (`CircuitBreakerTripped`, bot-status wordt `circuit_broken`)
   zodra de equity meer dan `max_drawdown_pct` onder de piekwaarde zakt.
   Dit gaat niet over één trade — het is "er is iets structureel mis met
   deze strategie/markt, stop met handelen en laat een mens kijken",
   ongeacht *waarom* de drawdown ontstond.
3. **Order-sanity-checks** (`check_order`) — weigert een order vóórdat hij
   de exchange bereikt als de notional onevenredig groot is t.o.v. de
   equity (`max_position_notional_pct`), de prijs absurd ver van de laatst
   bekende marktprijs ligt (`max_price_deviation_pct`), quantity/prijs niet
   positief zijn, of orders te snel na elkaar komen
   (`min_seconds_between_orders`). Dit is de laatste verdedigingslinie
   tegen een bug (een verkeerde fill-price-berekening, een eenheden-fout)
   die een echte order wordt.

Alle drie gooien een specifieke exception in plaats van een bool terug te
geven, zodat een aanroeper een getriggerde check niet per ongeluk kan
negeren door een returnwaarde te vergeten checken.
`tests/test_execution_risk.py` dekt alle drie de lagen (21 tests): triggers,
niet-triggers, randgevallen (exact op de grens) en de invoervalidatie van
`RiskLimits` zelf.

### Paper vs. live

- **Paper**: `PaperBroker` simuleert fills tegen de realtime prijs met
  exact hetzelfde kostenmodel als de backtester
  (`freqpanda_backtest.costs.TradingCosts`) — een paper-fill wordt dus op
  precies dezelfde manier berekend als een backtest-fill, alleen tegen
  live in plaats van historische prijzen. Geen exchange-call, geen order-id,
  geen echt geld.
- **Live**: `LiveBroker` plaatst echte market-orders via een
  geauthenticeerde CCXT-exchange-instance en gebruikt de door de exchange
  gerapporteerde gemiddelde fill-prijs (nooit de geschatte prijs) voor alle
  verdere stop-loss/take-profit/trailing-stop-tracking.

**De overstap naar live is met opzet nooit een impliciete bijwerking.** Drie
onafhankelijke barrières moeten allemaal genomen worden:

1. Op databaseniveau verplicht een CHECK-constraint
   (`bots_live_requires_credential` in de migratie) dat `mode = 'live'`
   altijd een `credential_id` heeft, en `mode = 'paper'` er nooit een heeft.
2. Op API-niveau (`freqpanda_api/schemas.py`, `BotCreateRequest`) moet een
   live-bot-aanvraag een expliciete `confirm_live: true` meesturen — een
   losse vlag naast `mode: "live"` zelf, zodat een client een paper-config
   niet per ongeluk live kan maken door alleen `mode` te wijzigen zonder
   zich bewust te zijn van de consequenties. Ontbreekt die vlag, dan wijst
   de API de aanvraag af (422) vóórdat er ooit een bot-rij bestaat.
3. Op orchestratieniveau start het aanmaken van een bot hem nooit — elke
   bot begint met `desired_status = 'stopped'`; pas een expliciete
   `POST /bots/{id}/start`-aanroep (die bij een live-bot opnieuw checkt dat
   de credential nog bestaat) zet hem aan het werk.

Er is geen enkel pad waarop het weglaten van een veld, een default, of een
kopie van een bestaande paper-configuratie een bot stilzwijgend live zet.

## Encryptie van exchange-API-keys

Zie `crypto.py`'s eigen docstring voor de volledige onderbouwing; kort:

- **Fernet** (`cryptography.fernet`) — symmetrische, geauthenticeerde
  encryptie (AES-128-CBC + HMAC-SHA256, met versie en timestamp in het
  token). Bewust een "saaie", goed doorgelichte keuze: dit is één-operator,
  encrypt-at-rest-en-decrypt-in-process-om-een-request-te-tekenen — geen
  multi-party- of public-key-scenario, dus geen reden om iets exotischers
  te gebruiken.
- De master key (env var `EXECUTION_MASTER_KEY`) leeft **uitsluitend** in
  de procesomgeving van de `api`- en `execution-supervisor`-services (via
  `.env` / docker-compose). Hij wordt **nooit** weggeschreven naar de
  database, een logregel, of de repository. `exchange_credentials.encrypted_api_key`
  / `_secret` / `_password` bevatten alleen het versleutelde Fernet-token —
  nooit plaintext, ook niet tijdelijk in een kolom die later "opgeschoond"
  wordt.
- Sleutel kwijt = alle opgeslagen credentials permanent onleesbaar. Dat is
  het **bedoelde** faalgedrag van "de sleutel staat niet naast de data die
  hij beschermt", geen bug. Bewaar de sleutel dus in een password-manager
  of secrets-store naast (niet: in) de VPS/`.env`.
- Genereren (eenmalig, bij setup):
  ```bash
  python -c "from freqpanda_execution.crypto import generate_master_key; print(generate_master_key())"
  ```
  Zet de output in `EXECUTION_MASTER_KEY` in `.env` — dezelfde waarde voor
  élk proces dat credentials leest of schrijft (de `api`-service schrijft
  ze bij het aanmaken van een credential; `execution-supervisor`'s
  bot-processen lezen ze bij het starten van een live bot).
- **Rotatie**: er is geen ingebouwde rotatie-tool. Om te roteren: alle
  bestaande credentials opnieuw aanmaken (decrypt met de oude key buiten
  band, re-encrypt met de nieuwe) vóór de oude key uit de omgeving
  verdwijnt, of — eenvoudiger voor een MVP — gebruikers hun exchange-API-
  keys laten intrekken/opnieuw aanmaken en opnieuw invoeren na de rotatie.
- Niets in deze module logt of retourneert ooit een ontsleuteld secret,
  behalve de ene call site die het nodig heeft om een CCXT-client te
  authenticeren (`broker.LiveBroker`, via `bot.build_bot`) — en die houdt
  het alleen in een lokale variabele, rechtstreeks doorgegeven aan de
  CCXT-client, nooit geprint of gelogd.

**Niet-custodial**: het platform houdt zelf nooit geld vast. De API-key die
een gebruiker aanlevert, autoriseert alleen handelen namens hen op hun
eigen exchange-account. Documentatie-aanbeveling (niet technisch
afdwingbaar vanuit dit platform): configureer de exchange-API-key zonder
withdrawal-permissie, zodat zelfs een gecompromitteerde key of een bug hier
nooit geld van de exchange kan laten wegvloeien — alleen handelen binnen
het account blijft mogelijk.

## Een bot starten/stoppen

Via de fase-5-API (de webapp uit fase 6 doet dit straks via dezelfde
endpoints):

```bash
# 1. Exchange-credential aanmaken (alleen nodig voor live bots)
curl -X POST http://localhost:8000/api/v1/exchange-credentials \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"exchange_id": "binance", "label": "main", "api_key": "...", "api_secret": "..."}'
# -> {"id": "cred_...", "exchange_id": "binance", "label": "main", ...}   (nooit de sleutels zelf terug)

# 2a. Paper-bot aanmaken
curl -X POST http://localhost:8000/api/v1/bots \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{
    "name": "ema-cross-btc-paper", "strategy_id": "strat_...", "exchange_id": "binance",
    "symbol": "BTC/USDT", "timeframe": "1h", "mode": "paper",
    "initial_capital": 1000, "max_drawdown_pct": 0.2
  }'

# 2b. Live-bot aanmaken (credential_id + confirm_live zijn allebei verplicht)
curl -X POST http://localhost:8000/api/v1/bots \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{
    "name": "ema-cross-btc-live", "strategy_id": "strat_...", "exchange_id": "binance",
    "symbol": "BTC/USDT", "timeframe": "1h", "mode": "live", "credential_id": "cred_...",
    "confirm_live": true, "initial_capital": 500, "max_drawdown_pct": 0.1
  }'

# 3. Starten (zet desired_status='running' -- de supervisor spawnt het subprocess)
curl -X POST http://localhost:8000/api/v1/bots/bot_.../start -H "X-API-Key: $API_KEY"

# 4. Status/positie/PnL volgen
curl http://localhost:8000/api/v1/bots/bot_...        -H "X-API-Key: $API_KEY"
curl http://localhost:8000/api/v1/bots/bot_.../state  -H "X-API-Key: $API_KEY"
curl http://localhost:8000/api/v1/bots/bot_.../trades -H "X-API-Key: $API_KEY"
curl http://localhost:8000/api/v1/bots/bot_.../events -H "X-API-Key: $API_KEY"

# 5. Stoppen (zet desired_status='stopped' -- de supervisor beëindigt het subprocess netjes)
curl -X POST http://localhost:8000/api/v1/bots/bot_.../stop -H "X-API-Key: $API_KEY"
```

`freqpanda_api/routers/bots.py` bevat alle endpoints; zie de Swagger UI
(`/docs`) op de draaiende API voor het volledige schema.

### Lokaal draaien zonder Docker (ontwikkeling/debuggen)

```bash
export SUPABASE_DB_URL=postgresql://...
export EXECUTION_MASTER_KEY=...   # zie hierboven
psql "$SUPABASE_DB_URL" -f migrations/0003_create_execution_tables.sql

# Eén bot direct starten (zonder supervisor -- handig om te debuggen):
python -m freqpanda_execution.runner bot_abc123

# Of de supervisor, die alle bots met desired_status='running' beheert:
python -m freqpanda_execution.supervisor
```

Een bot-proces stopt netjes op SIGTERM/SIGINT (`runner.py` registreert
signal-handlers die `Bot.stop()` aanroepen) — de lopende candle-afhandeling
maakt zich af en schrijft zijn state weg voordat het proces stopt.

### Vereisten voordat een bot kan starten

- Het symbool/timeframe/exchange-combinatie moet al historische OHLCV-data
  hebben via fase 2's databackfill (`build_bot` leest de seed-geschiedenis
  uit dezelfde Postgres-tabel, nooit live opgehaald) — anders faalt het
  starten met een duidelijke foutmelding in plaats van met een lege
  indicatorberekening te beginnen.
- De onderliggende strategie (fase 1) moet al bestaan (`strategy_id`
  verwijst naar een rij in `strategies`).
- Voor een live bot: een geldige, bij deze gebruiker horende
  exchange-credential.

## Tests

```bash
pytest tests/test_execution_*.py tests/test_live_interpreter.py tests/test_api_router_bots.py -v
```

- `test_execution_risk.py` — de expliciet vereiste risk-middleware-tests:
  hard-stop-loss-triggers, circuit-breaker-triggers (inclusief een
  stijgende piek vóór het triggeren), en alle order-sanity-checks.
- `test_live_interpreter.py` — de kernclaim "geen drift tussen backtest en
  live": candle-voor-candle via `LivePositionTracker` versus in één keer
  via `run_strategy()`, over meerdere seeds en strategievormen.
- `test_execution_feed.py` — de polling-feed en de dedup/trim-logica die
  beide feed-paden delen, tegen een nep-exchange (geen netwerk).
- `test_execution_broker.py` — paper-fills (kostenmodel) en live-fills
  (CCXT-call-vorm, fallback-logica), tegen een gemockte CCXT-exchange.
- `test_execution_crypto.py` — encrypt/decrypt-roundtrip, verkeerde
  sleutel, corrupte ciphertext, ontbrekende sleutel.
- `test_execution_repository.py` — elke DB-functie tegen een gemockte
  psycopg2-cursor (zelfde patroon als fase 5's repository-tests).
- `test_execution_bot.py` — de `Bot`-orchestratie end-to-end met een echte
  `PaperBroker`/`RiskMiddleware`/`LivePositionTracker`, alleen de
  `repository`-DB-laag gemockt: entry, exit, de onafhankelijke
  hard-stop-loss, order-rejection-rollback, circuit-breaker-propagatie, en
  de statusovergangen van `run()`.
- `test_api_router_bots.py` — de nieuwe `/api/v1/bots`- en
  `/api/v1/exchange-credentials`-endpoints, inclusief de live-transitie-
  validatie (`confirm_live`, credential-ownership).

De websocket-feed (`ccxt.pro`/`watch_ohlcv`) heeft een echte
exchange-verbinding nodig en wordt hier niet getest — zie `feed.py`'s eigen
docstring.

## Niet in scope (met opzet)

- Geen nieuwe strategielogica — `live_interpreter.py` hergebruikt fase 1's
  `compute_indicators`/`evaluate_condition` ongewijzigd.
- Geen nieuwe backtest-functionaliteit.
- Geen sleutelrotatie-tooling (zie "Encryptie" hierboven).
- Geen multi-exchange-portfolio-netting of cross-bot-risicobeheer — elke
  bot beheert zijn eigen equity/positie/risicolimieten volledig los van
  elke andere bot, ook als ze dezelfde credential delen.
