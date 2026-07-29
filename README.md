# ATSift

**Pick a timeframe. Hit run. Get fresh roles.**

Sweeps ~18,000 company job boards across six applicant-tracking systems, keeps
only the non-senior roles that match a boolean search, and screens each one for
US location and F-1/OPT eligibility.

## The idea

Checking career pages one at a time is slow, and most listings don't say up
front whether a role is US-based or open to OPT candidates. ATSift asks for one
input — how far back to look — and answers those two questions across thousands
of boards at once.

The timeframe drives the scan *and* the results. It is not a filter applied
afterwards; the window you pick is the window the postings are drawn from.

## How a scan works

Each stage costs far more than the one before it, so each only ever sees what
survived the last:

```
fetch board  →  boolean search  →  time window  →  location screen  →  LLM
   18k          title keywords      your choice     regex, free       expensive
```

1. **Sweep** every board in the catalog concurrently.
2. **Boolean search** on the title: category keywords AND NOT seniority terms.
3. **Time window** — drop anything outside the chosen timeframe.
4. **Location screen** — pattern matching settles the clear cases for free.
5. **LLM** — only the survivors, and only ambiguous locations, reach the model.

## Architecture

```
Greenhouse ─┐
Ashby       │
Lever       ├─► scanner/ (Flask) ─► data/jobs_store.json ─► web/ (Next.js)
SmartRecrtrs│         │                                          │
Workable    │         └─► Ollama llama3.2:3b                     └─► AI Job Scout
Workday    ─┘             (per-job screening)                        (OpenRouter)
```

Two LLMs, split by what each is good at. The **local** model does bulk per-job
screening, where volume would make API pricing hurt and latency doesn't matter.
The **hosted** model powers the conversational scout, where quality and speed
do.

## Layout

```
├── app.py                  Entry point
├── scanner/
│   ├── config.py           Settings, paths, the analysis schema
│   ├── boolean_search.py   ← the filter that defines the product
│   ├── ats/                One adapter per board, plus dispatch
│   ├── scan.py             The sweep
│   ├── analysis.py         Ollama screening, cached by fingerprint
│   ├── locations.py        US screening; LLM only for genuine ambiguity
│   ├── dates.py            Timestamp parsing and the window
│   ├── status.py store.py  Live progress; job and viewed stores
│   └── web.py              Flask routes
├── data/                   Company catalogs and JSON caches
├── docs/                   Boolean search, endpoints, product spec
├── llm/                    Pristine copies of the two LLM integrations
├── tests/                  Backend tests
└── web/                    Next.js 16 dashboard
```

## Running it

### Scanner

```bash
python3 -m pip install -r requirements.txt
python3 app.py                 # http://127.0.0.1:5000
```

Needs Ollama for analysis:

```bash
ollama pull llama3.2:3b
```

Set `LOGO_DEV_PUBLISHABLE_KEY`, `BRANDFETCH_SECRET_API_KEY` and
`SCANNER_API_TOKEN` in `.env`.

### Dashboard

```bash
cd web
npm install
npm run dev                    # http://localhost:3000
```

`web/.env.local`:

```
SCANNER_API_BASE_URL=http://127.0.0.1:5000
SCANNER_API_TOKEN=<same value as the scanner's>
OPENROUTER_API_KEY=<key>
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
```

With no scanner reachable the dashboard still works against the packaged
snapshot, and hides the Run button rather than offering an action that fails.

## API

| Route | |
|---|---|
| `GET /api/health` | Liveness; no token required |
| `GET /api/meta` | Categories, catalogs, timeframe options |
| `GET /api/status` | Live scan progress |
| `GET /api/jobs?lookback_hours=24` | Stored results |
| `POST /api/scan` | `{lookback_hours, dataset, categories}` |
| `POST /api/scan/stop` | Cancel a running scan |
| `POST /api/jobs/viewed` | `{uid}` |

`/api/*` requires `Authorization: Bearer $SCANNER_API_TOKEN` whenever
`SCANNER_API_TOKEN` is set. Leave it unset only on `127.0.0.1`.

## Data

| File | |
|---|---|
| `data/companies.csv` | 17,167 companies — greenhouse 5,748 · workable 3,480 · ashby 3,299 · smartrecruiters 2,377 · lever 2,263 |
| `data/companies_workday.csv` | 1,097 Workday tenants, kept separate because the slug is a full board URL |
| `data/analysis_cache.json` | LLM analyses keyed by a fingerprint of prompt version + model + job fields |

Every company was deduplicated by ATS + slug and live-checked for a resolvable
US posting before being kept.

## Tests

```bash
python3 -m pytest tests/ -q     # 19 tests
cd web && npx tsc --noEmit
```

## Notes

- **The scanner can't be serverless.** It is long-running and stateful, holds a
  cancel event in memory, streams progress, and needs Ollama resident. Only
  `web/` deploys.
- **Availability is decided by a health probe**, not by whether a URL is
  configured — a URL that merely parses is not a reachable scanner.
- **`MAX_ANALYSIS_PER_SCAN`** (default 120) bounds worst-case scan time, since
  the local model is by far the slowest step. Matches beyond it are returned
  without an AI breakdown.
