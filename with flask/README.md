# ATSift

ATSift scans public Greenhouse, Ashby, Lever, SmartRecruiters, Workable, and Workday job boards, filters newly published engineering roles, and runs private job-description analysis through local Ollama.

## Modern application structure

- `app.py` — Python scanner and JSON API
- `companies.csv` — 16,401-company catalog across five ATS platforms
- `companies_2500.csv` — focused 2,500-company catalog with 500 companies per ATS
- `companies_verified_us.csv` — 8,011 verified U.S. companies across the five non-Workday ATS platforms
- `companies_seed.csv` — 1,952 companies converted from the supplied TypeScript seed catalog, including 34 Workday career sites
- `jobs_store.json` — local job cache
- `viewed_jobs.json` — durable record of jobs opened from the Apply button
- `analysis_cache.json` — local Ollama analysis cache
- `web/` — Next.js 16 + React 19 interface
- `templates/index.html` — retained legacy Flask interface for compatibility

## Start the complete app

```bash
python3 -m pip install -r requirements.txt
cd web
npm install
npm run dev
```

Open `http://localhost:3000`. The command runs both the Next.js interface and the scanner API. AI Job Scout can use local Ollama at `http://localhost:11434` with `llama3.2:3b`, or an online Meta Llama model through OpenRouter when `OPENROUTER_API_KEY` is configured in `web/.env.local`. The scout turns a natural-language request into a read-only search plan over recently scraped jobs, then returns verified ATS application links. It defaults to the last 12 hours when the prompt does not include a timeframe and supports explicit windows up to 72 hours.

The dataset dropdown selects the full 16,401-company catalog, focused 2,500-company catalog, verified U.S. 8,011-company catalog, or converted 1,952-company seed catalog for scanning and displayed results. The seed catalog includes 34 Workday career sites and supports their public external-job feeds. The scanner fetches companies concurrently and distributes requests across ATS providers. Set `ATSIFT_FETCH_WORKERS` before starting the app to change the default concurrency of 15 workers.

## API

- `GET /api/health`
- `GET /api/status`
- `GET /api/jobs?lookback_hours=48&dataset=focused_2500`
- `POST /api/jobs/viewed` with `{ "uid": "ashby:company:job-id" }`
- `POST /api/scan` with `{ "lookback_hours": 48, "dataset": "focused_2500" }`

The legacy Flask page remains available at `http://127.0.0.1:5000` when the API is running.
