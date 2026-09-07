# freqpanda_api — fase 5: backend API + job-queue

FastAPI-backend die fase 1 t/m 4 aan elkaar knoopt: strategie-CRUD,
backtest-/optimalisatie-jobs (asynchroon, via een Redis-wachtrij),
resultaten in Supabase/Postgres, en endpoints om die resultaten weer op te
vragen en te vergelijken. Klaar om door een webapp (fase 6) aangesproken te
worden.

Los van UI, live trading, en een volledig multi-user-systeem — maar zo
gebouwd dat dat laatste een toevoeging is, geen herontwerp (zie
"Multi-user later" hieronder).

## Snel starten (lokaal, zonder Docker)

```bash
pip install -e ".[dev]"
psql "$SUPABASE_DB_URL" -f migrations/0001_create_ohlcv_candles.sql
psql "$SUPABASE_DB_URL" -f migrations/0002_create_api_tables.sql

export SUPABASE_DB_URL=postgresql://...
export API_KEYS=dev-key
export REDIS_URL=redis://localhost:6379/0

uvicorn freqpanda_api.main:app --reload &
rq worker --url "$REDIS_URL" freqpanda &
```

API-documentatie (Swagger UI): `http://localhost:8000/docs`.

## Snel starten (Docker Compose)

```bash
cp .env.example .env   # vul SUPABASE_DB_URL en API_KEYS in
docker compose up -d --build
curl http://localhost:8000/health
```

`docker compose up -d --scale worker=3` draait drie workerprocessen op
dezelfde wachtrij voor meer doorvoer — zie "Job-queue-architectuur"
hieronder.

## Architectuur

```
freqpanda_api/
  main.py                FastAPI-app: routers, exception handlers, /health
  config.py                Settings uit env vars
  auth.py                  API-key-verificatie (X-API-Key header)
  db.py                    Per-request Postgres-connectie (hergebruikt freqpanda_data.db.get_connection)
  ids.py                    Prefixed id's (strat_..., job_...)
  schemas.py                Request/response-modellen (StrategyDefinition zelf is de strategie-schema)
  serializers.py            Repository-record -> response-model
  repositories/
    strategies.py            CRUD op de strategies-tabel
    jobs.py                  Job-bookhouding (pending/running/completed/failed)
    results.py                Backtest-/optimalisatie-resultaten wegschrijven en lezen
  routers/
    strategies.py, backtests.py, optimizations.py, compare.py
  jobs/
    queue.py                RQ-wachtrij-setup
    tasks.py                 De functies die de worker daadwerkelijk uitvoert
migrations/
  0002_create_api_tables.sql   strategies, jobs, backtest_results, optimization_results
docker/Dockerfile          Eén image voor zowel API als worker
docker-compose.yml          api + worker + redis
```

## Endpoints

Alle `/api/v1/*`-endpoints vereisen de `X-API-Key`-header. Volledige,
interactieve documentatie op `/docs` (OpenAPI/Swagger, automatisch door
FastAPI gegenereerd uit de type-hints/Pydantic-modellen hieronder).

| Methode | Pad | Omschrijving |
|---|---|---|
| POST | `/api/v1/strategies` | Strategie aanmaken (body = fase-1 `StrategyDefinition`) |
| GET | `/api/v1/strategies` | Eigen strategieën lijsten |
| GET | `/api/v1/strategies/{id}` | Eén strategie ophalen |
| PUT | `/api/v1/strategies/{id}` | Strategie updaten (volledige definitie vervangen) |
| DELETE | `/api/v1/strategies/{id}` | Strategie verwijderen |
| POST | `/api/v1/strategies/{id}/backtests` | Backtest-job starten (async, 202) |
| GET | `/api/v1/strategies/{id}/backtests` | Backtests voor deze strategie (status + metrics-samenvatting) |
| GET | `/api/v1/backtests/{job_id}` | Backtest-detail (status + metrics + trades + equity-curve) |
| POST | `/api/v1/strategies/{id}/optimizations` | Optimalisatie-job starten (async, 202) |
| GET | `/api/v1/strategies/{id}/optimizations` | Optimalisaties voor deze strategie |
| GET | `/api/v1/optimizations/{job_id}` | Optimalisatie-detail (per-venster in-sample/out-of-sample + eindresultaat) |
| POST | `/api/v1/compare` | Metrics van meerdere voltooide backtest-jobs naast elkaar |
| GET | `/health` | Health-check, geen API-key nodig |

Elk `POST .../backtests` of `.../optimizations` geeft direct een
`{id, status: "pending", ...}` terug — poll `GET .../backtests/{job_id}`
(of `/optimizations/{job_id}`) tot `status` `"completed"` of `"failed"` is.

## Job-queue-architectuur

**Waarom RQ (Redis Queue) en niet Celery/een aparte broker-cluster.** Voor
een single-VPS-opzet met een handvol jobtypes is Celery's
routing/exchanges/aparte broker-configuratie meer dan nodig — het voegt
operationele complexiteit toe (meer bewegende delen, meer om te
monitoren) zonder een voordeel dat hier telt (geen multi-datacenter
routing, geen honderden worker-typen). RQ is één Redis-instantie plus
platte Python-functies als jobs: `pip install rq`, `rq worker`, klaar. Als
de bottleneck ooit een enkele grote Redis-instantie wordt (zeer
onwaarschijnlijk voor dit gebruik — jobs zijn er tientallen tot honderden
per dag, niet per seconde), is Celery de voor de hand liggende
vervolgstap; RQ's simpele model maakt het makkelijk om dat pad in te slaan
zonder de rest van de applicatie te herschrijven (de job-functies zelf
veranderen niet).

**Hoe een job door het systeem gaat:**

1. `POST /api/v1/strategies/{id}/backtests` (of `.../optimizations`):
   - valideert dat de strategie bestaat en van de aanroeper is
   - schrijft een rij in `jobs` (status `pending`) met de request-payload
     als `jsonb`
   - roept `queue.enqueue(run_backtest_job, job.id, job_id=job.id)` aan —
     RQ serialiseert dit als "roep deze functie aan met dit argument" en
     zet het in een Redis-lijst
   - geeft direct de job terug (geen wachten op de daadwerkelijke run)
2. Een workerproces (`rq worker ... freqpanda`, één of meer instanties)
   haalt de taak van de wachtrij en roept `run_backtest_job(job_id)` aan in
   `jobs/tasks.py`.
3. De taak:
   - opent zijn **eigen** Postgres-connectie (een worker is een apart
     proces, kan geen request-scoped connectie van de API hergebruiken)
   - zet de job op `running`
   - leest de strategie-definitie en de job-payload
   - leest OHLCV via `freqpanda_data.fetch_ohlcv_dataframe` (fase 2's
     opslag — de taak haalt zelf **niets** live van de exchange; als de
     gevraagde periode niet gebackfilld is, faalt de job met een
     duidelijke foutmelding in plaats van alsnog een live CCXT-call te
     doen, wat een asynchrone job onvoorspelbaar traag zou maken en fase
     2's eigen rate-limit-beheer zou omzeilen)
   - roept `freqpanda_backtest.backtest()` (of
     `freqpanda_optimize.optimize()` + `refit_on_full_history()`) aan —
     precies de publieke functies uit die fases, niets herïmplementeerd
   - schrijft het resultaat weg via `repositories/results.py`
   - zet de job op `completed`, of op `failed` met de foutmelding als er
     iets misging

De `jobs`-tabel in Postgres is de **enige** bron van waarheid voor
job-status die clients zien — niet Redis. Redis/RQ is puur het
transportmechanisme ("voer deze functie ooit uit, op een worker"); als
Redis herstart, verlies je hooguit nog-niet-opgepakte jobs (die blijven
`pending` en moeten opnieuw aangevraagd worden), maar nooit de historie van
al voltooide jobs.

**Meerdere workers.** Elke `rq worker`-instantie luistert onafhankelijk op
dezelfde named queue (`freqpanda`, configureerbaar via `JOB_QUEUE_NAME`);
Redis' `BLPOP` zorgt dat elke job precies één keer wordt opgepikt. Meer
doorvoer = meer workerinstanties starten
(`docker compose up -d --scale worker=3`), zonder verdere configuratie.

**Timeouts.** `JOB_TIMEOUT_SECONDS` (standaard 1800s) is het per-job
hard limit dat RQ afdwingt — een job die vastloopt of te lang duurt wordt
afgebroken in plaats van voor altijd een workerslot te bezetten. Dit is
ook wat vereiste 5 ("configureerbaar optimalisatie-budget... zodat dit
past in een job-queue zonder oneindig te draaien") in de praktijk afdwingt,
bovenop `n_trials`/`timeout_seconds` die fase 4's `optimize()` zelf al
kent.

## Een nieuw job-type toevoegen

Bijvoorbeeld: een job die een fase-4 `generate_variants()`-batch genereert
én evalueert (in plaats van dat handmatig via een los script te doen).

1. **Job-type toevoegen aan het schema**: in
   `migrations/0003_....sql`, breid de `check`-constraint op
   `jobs.job_type` uit (`check (job_type in ('backtest', 'optimization', 'generate_and_evaluate'))`),
   en maak een resultaten-tabel naar smaak (of hergebruik
   `backtest_results` als de uitkomst daar al in past).
2. **Taakfunctie**: een nieuwe functie in `jobs/tasks.py`
   (`run_generate_and_evaluate_job(job_id: str)`), zelfde vorm als de
   twee bestaande: eigen connectie openen, job ophalen, `mark_running`,
   het echte werk doen via de publieke fase 1-4-functies, resultaat
   opslaan, `mark_completed`/`mark_failed`.
3. **Request/response-modellen**: een nieuw Pydantic-model in
   `schemas.py` voor de job-parameters (bv. `GenerateAndEvaluateRequest`
   met `bounds`, `n`, `metric`).
4. **Router**: een nieuwe `routers/generate.py` (of een endpoint
   toevoegen aan een bestaande router) die de payload valideert, een
   job aanmaakt via `jobs_repo.create_job(conn, "generate_and_evaluate", ...)`,
   en `get_queue().enqueue(run_generate_and_evaluate_job, job.id, job_id=job.id)`
   aanroept.
5. Router registreren in `main.py`.

Niets in `jobs/queue.py`, `db.py`, `auth.py` of de bestaande routers hoeft
aangepast te worden — die kennen alleen "een job heeft een type, een
payload, en een taakfunctie die er iets mee doet."

## Multi-user later

Er is nu geen gebruikersbeheer — één of meer statische API-keys
(`API_KEYS`, komma-gescheiden env var), gecontroleerd in `auth.py`. Elke
rij die deze API schrijft (`strategies`, `jobs`) heeft een `created_by`-
kolom die de sha256-hash van de gebruikte key bevat (nooit de key zelf) —
elke lees/schrijf-operatie is al gescoped op die waarde. Een latere
upgrade naar echte user-accounts betekent:

- een `users`-tabel toevoegen en `require_api_key`'s lichaam vervangen
  door een echte lookup (sessie/JWT/wat dan ook) die een user-id teruggeeft
  in plaats van een key-hash
- `created_by` interpreteren als user-id in plaats van key-hash

Verder hoeft niets te veranderen: elke repository-functie en elke router
behandelt `created_by` al als een ondoorzichtige eigenaar-identifier, nooit
als "de enige gebruiker van het systeem".

## Deployen op een Hetzner Ubuntu-VPS

Uitgaand van een kale Ubuntu 22.04/24.04-VPS (bv. Hetzner CX-serie) en een
bestaand Supabase-project.

1. **Docker installeren** (op de VPS, als root of via sudo):
   ```bash
   curl -fsSL https://get.docker.com | sh
   usermod -aG docker $USER   # opnieuw inloggen om dit effect te laten hebben
   ```

2. **Repository ophalen**:
   ```bash
   git clone <repo-url> freqpanda && cd freqpanda
   ```

3. **Configureren**:
   ```bash
   cp .env.example .env
   nano .env   # SUPABASE_DB_URL invullen, API_KEYS naar een echte random waarde
   ```
   Genereer een sterke key met bv. `openssl rand -hex 32`.

4. **Database-migraties draaien** (eenmalig, tegen Supabase — vanaf de VPS
   of lokaal, hoeft niet vanuit een container):
   ```bash
   psql "$(grep SUPABASE_DB_URL .env | cut -d= -f2-)" -f migrations/0001_create_ohlcv_candles.sql
   psql "$(grep SUPABASE_DB_URL .env | cut -d= -f2-)" -f migrations/0002_create_api_tables.sql
   ```

5. **Starten**:
   ```bash
   docker compose up -d --build
   docker compose ps        # api, worker, redis moeten alle drie "healthy"/"running" zijn
   curl http://localhost:8000/health
   ```

6. **Poort 8000 naar buiten toe beschikbaar maken.** Voor een MVP volstaat
   het direct openzetten van poort 8000 in Hetzner's cloud-firewall
   (Hetzner Cloud Console -> Firewalls). Voor een publiek adres met TLS,
   zet een reverse proxy ervoor in plaats van uvicorn direct bloot te
   stellen:
   ```bash
   apt-get install -y nginx certbot python3-certbot-nginx
   ```
   Nginx proxy_pass naar `http://127.0.0.1:8000`, dan
   `certbot --nginx -d jouw-domein.nl` voor een Let's Encrypt-certificaat.
   (Dit valt buiten fase 5's scope — hier alleen genoemd als het voor de
   hand liggende vervolg zodra de webapp uit fase 6 dit adres nodig heeft.)

7. **Updates uitrollen**:
   ```bash
   git pull
   docker compose up -d --build   # herbouwt en herstart api + worker; redis blijft draaien
   ```

8. **Logs/monitoring**:
   ```bash
   docker compose logs -f api
   docker compose logs -f worker
   ```
   `restart: unless-stopped` (in `docker-compose.yml`) zorgt dat alle drie
   de services een VPS-reboot overleven zonder verdere systemd-configuratie.

## Tests

```bash
pytest tests/test_api_*.py -v
```

- `test_api_auth.py` — API-key-verificatie: geldig/ongeldig/ontbrekend,
  en dat de ruwe key nooit in de opgeslagen `created_by`-waarde voorkomt.
- `test_api_repo_*.py` — elke repository-functie tegen een gemockte
  psycopg2-cursor (zelfde patroon als fase 2's databaselaag-tests): juiste
  SQL/parameters, juiste mapping van rijen terug naar records.
- `test_api_tasks.py` — de workerfuncties end-to-end tegen echte
  fase 1-4-code en synthetische OHLCV-data, met alleen de DB-laag gemockt:
  bewijst dat een job daadwerkelijk `backtest()`/`optimize()` aanroept en
  het juiste resultaat opslaat, en dat een lege OHLCV-set de job naar
  `failed` zet met een duidelijke foutmelding.
- `test_api_routers.py` — de HTTP-laag met een echte FastAPI `TestClient`
  en echte auth, DB-dependency overridden en repository-calls gemockt:
  bewijst request-validatie, statuscodes en response-vorm.
- `test_api_queue_integration.py` — een echte lokale `redis-server` plus
  een echte RQ `Queue`/`SimpleWorker`: bewijst dat het queue-mechanisme
  zelf (enqueue -> dequeue -> uitvoeren) werkt, niet alleen de taakfunctie
  in isolatie.
