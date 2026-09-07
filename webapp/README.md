# freqpanda webapp — fase 6

Next.js-webapp (App Router, TypeScript) om strategieën te bouwen, backtests en
optimalisaties te starten, en resultaten te bekijken/vergelijken — gebouwd
tegen de echte fase-5 API (geen mock). Deployt op Vercel.

## Snel starten (lokaal)

Vereist een draaiende fase-5 backend (API + Redis + worker + Postgres —
zie `freqpanda_api/README.md`).

```bash
cp .env.local.example .env.local
# BACKEND_API_URL en BACKEND_API_KEY invullen (zie hieronder)

npm install
npm run dev
```

Open `http://localhost:3000`.

## Env-variabelen

| Variabele | Waar | Omschrijving |
|---|---|---|
| `BACKEND_API_URL` | server-only | Basis-URL van de fase-5 API, bv. `http://localhost:8000` of je Hetzner-VPS-adres. |
| `BACKEND_API_KEY` | server-only | Eén van fase 5's `API_KEYS`. |

Beide staan **niet** met `NEXT_PUBLIC_` prefix en komen dus nooit in de
browser-bundle terecht — zie "Architectuur: de proxy-route" hieronder voor
waarom.

Op Vercel: zet beide als environment variables in het project (Settings →
Environment Variables) voor Production/Preview/Development naar wens.

## Architectuur: de proxy-route

De browser praat nooit rechtstreeks met de fase-5 API. Elke fetch gaat naar
`/api/proxy/*` (`src/app/api/proxy/[...path]/route.ts`), een Next.js Route
Handler die:

1. `BACKEND_API_URL`/`BACKEND_API_KEY` server-side leest (nooit naar de
   client verzonden)
2. het verzoek doorstuurt naar `${BACKEND_API_URL}/api/v1/<path>` met de
   `X-API-Key`-header erbij
3. de response 1-op-1 teruggeeft

Dit betekent: de API-key staat nergens in de browser (niet in de bundle,
niet in het Network-tabblad), en een latere multi-user-login kan precies op
deze plek een sessie-check toevoegen zonder dat er iets aan de
client-componenten hoeft te veranderen — precies de eis dat het ontwerp een
loginsysteem niet onmogelijk maakt.

## Paginastructuur

```
/                                strategie-overzicht (backtests-count + beste Sharpe/return per strategie)
/strategies/new                  strategie-builder (aanmaken)
/strategies/[id]                 detail: definitie, risk, backtests-lijst, optimalisaties-lijst
/strategies/[id]/edit            strategie-builder (bewerken, vooringevuld)
/backtests/[jobId]                status (pollend) -> equity-curve, kernmetrics, trade-tabel
/optimizations/[jobId]           status (pollend) -> in-sample/out-of-sample per venster, aanbevolen parameters
/compare                         meerdere backtest-job-id's naast elkaar (grafiek + tabel)
```

## State-management

**TanStack Query** voor alle server-state (fetchen, caching, polling) — geen
Redux/Zustand: er is geen complexe client-only state die dat zou
rechtvaardigen, en React Query's `refetchInterval` is precies wat
statuspollen voor backtest-/optimalisatie-jobs nodig heeft
(`src/lib/use-job-polling.ts`, stopt automatisch zodra een job
`completed`/`failed` is). Lokale formulierstate (de strategie-builder, de
job-start-formulieren) is gewoon React `useState` — er is niets dat gedeeld
hoeft te worden buiten die ene component.

## Strategy builder: bewuste v1-scope

Fase 1's schema staat willekeurig geneste and/or/not-bomen toe. Een visuele
builder voor willekeurige bomen is behoorlijk wat interface voor een eerste
versie; deze builder ondersteunt in plaats daarvan **één platte groep
vergelijkingen per kant** (entry/exit), gecombineerd met één AND/OR — dat
dekt allebei fase 1's eigen voorbeeldstrategieën (een kale crossover, en een
AND van twee vergelijkingen). Bij het **bewerken** van een strategie met een
complexere conditie (geneste groepen, of een `not`) toont de builder een
duidelijke waarschuwing en een placeholder-conditie in plaats van de
originele logica stilzwijgend te verminken (`src/lib/strategy-draft.ts`,
`definitionToDraft`/`conditionToGroup`). Uitbreiden naar geneste groepen is
een aparte, latere stap; dit is nu gedocumenteerd als grens, niet verzwegen.

De indicator-catalogus (`src/lib/indicator-catalog.ts`) is een handmatige
spiegeling van `freqpanda_strategy.indicators.INDICATOR_REGISTRY` — dat is
Python-interpreterkennis, niet iets wat de API over HTTP blootlegt. Een
nieuwe indicator toevoegen aan fase 1 betekent dus ook een entry toevoegen
in dit bestand.

## Design

Donker "terminal"-thema (zie `src/app/globals.css` voor het volledige
tokensysteem): amber als merk-/interactiekleur (een knipoog naar
phosphor-CRT-handelsterminals), groen/rood strikt gereserveerd voor
winst/verlies-semantiek. Space Grotesk voor koppen, Inter voor UI-tekst,
JetBrains Mono met tabular figures voor alle cijfers (tabellen, metrics) —
zodat kolommen met getallen verticaal uitlijnen, zoals op een echt
handelsscherm.

De categorale kleurenset voor de vergelijkingsgrafiek (`src/lib/series-colors.ts`)
en de groen/rood-kleuren voor winst/verlies zijn gevalideerd met de
dataviz-skill's `validate_palette.js` tegen dit thema's exacte
paneel-achtergrondkleur (`#12161D`) — geen fixed 8-hue-set is zomaar
overgenomen zonder de contrast-/CVD-checks opnieuw te draaien.

## Bekende, met opzet niet opgeloste dingen (v1)

- Geen paginering op de strategieënlijst of de trades-tabel (wel een
  scroll-container met vaste hoogte voor trades) — prima tot een paar
  honderd rijen, een taak voor later bij groter gebruik.
- Het dashboard doet één losse `listBacktests`-call per strategie (om
  "beste Sharpe tot nu toe" te tonen) — prima voor tientallen strategieën,
  zou bij honderden een samengevoegd backend-endpoint rechtvaardigen.

## Deployen op Vercel

```bash
vercel link      # of importeer de repo via het Vercel-dashboard, root: webapp/
vercel env add BACKEND_API_URL
vercel env add BACKEND_API_KEY
vercel deploy --prod
```

Zorg dat `BACKEND_API_URL` publiek bereikbaar is vanaf Vercel's
edge-netwerk (dus niet `localhost`) — in productie het adres van de fase-5
Hetzner-VPS (zie `freqpanda_api/README.md`, sectie Deployen), bij voorkeur
achter HTTPS.

## Getest tegen de echte backend

Deze app is ontwikkeld en handmatig doorgetest (Playwright, tegen een echt
lokaal draaiende fase 1-5 stack: Postgres, Redis, de FastAPI-app, een
RQ-worker) — niet tegen een losstaande mock. Die sessie legde onderweg twee
echte fase-5-bugs bloot die in `freqpanda_api` zijn gefixed:

- `profit_factor: Infinity` (een strategie zonder verlieztrades) brak de
  jsonb-opslag van backtest-resultaten, omdat Postgres' `jsonb`-type de
  niet-standaard `Infinity`/`NaN`-JSON-tokens weigert. Fase 5's
  `results.py` sanitiseert nu niet-eindige floats naar `null` vóór opslag.
- Een mislukte job liet de Postgres-transactie in aborted-status achter,
  waardoor de daaropvolgende `mark_failed`-update zelf ook faalde — de job
  bleef voor altijd op "running" staan. `jobs/tasks.py` doet nu een
  `rollback()` vóór het schrijven van de foutstatus.

Zie de commit-historie in `freqpanda_api/` voor de details.
