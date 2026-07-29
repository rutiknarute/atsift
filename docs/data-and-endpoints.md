# Preserved data + ATS endpoints

Reference for the rebuild. The adapters themselves were deleted; these are the
facts they encoded.

## Company catalogs

Both files are `name,ats,slug` with a header row.

| File | Rows | Contents |
|---|---|---|
| `data/companies.csv` | 17,167 | greenhouse 5,748 · workable 3,480 · ashby 3,299 · smartrecruiters 2,377 · lever 2,263 |
| `data/companies_workday.csv` | 1,097 | workday 1,097 — kept separate, different API shape |
| `data/all_companies.csv` | — | earlier unverified superset, pre-dedup |

Every company in the two catalogs was deduplicated by `ats` + `slug` and
live-checked against its own board for at least one resolvable US posting
before being kept. Treat them as verified; don't re-derive from
`all_companies.csv`.

`slug` meaning differs by ATS:

- **greenhouse / ashby / lever / smartrecruiters / workable** — a board token,
  e.g. `0g`, substituted into the endpoint below.
- **workday** — a full board URL, e.g.
  `https://23andme.wd5.myworkdayjobs.com/23`. Workday tenants have no uniform
  slug, which is why the dataset is separate.

## Endpoints

```
Greenhouse       https://boards-api.greenhouse.io/
Ashby            https://api.ashbyhq.com/
Lever            https://api.lever.co/v0/postings      (EU: https://api.eu.lever.co/v0/postings)
SmartRecruiters  https://api.smartrecruiters.com/v1/companies/
Workable         https://www.workable.com/api/accounts/
Workday          per-tenant board URL from the slug column
```

All are public, unauthenticated job-board APIs. Lever has a separate EU host —
the old adapter tried the US host and fell back to EU.

## Other preserved data

| File | What it is |
|---|---|
| `data/analysis_cache.json` (1.7 MB) | LLM analyses keyed by fingerprint. Keep it — every hit is inference not re-paid. |
| `data/jobs-snapshot.json` (978 KB) | Packaged snapshot of scanned jobs; let the UI render before any scan runs. |
| `data/viewed_jobs.json` | Viewed-job UIDs, format `ats:company:job-id`. |
| `data/brandfetch_logo_cache.json` | Resolved company logo URLs (Brandfetch, logo.dev fallback). |

## Cache fingerprinting

`analysis_cache.json` is keyed by a SHA-256 of:

```
ANALYSIS_PROMPT_VERSION | OLLAMA_MODEL | title | location | team |
salary_context | description[:8000]
```

Both the prompt version and the model are in the key, so changing either
invalidates cleanly rather than serving analyses from a different prompt. Keep
this scheme or the cache is worthless.

## Credentials

`.env` (scanner) and `.env.local.web` (frontend) are preserved with real keys —
both are gitignored, keep them that way.

```
LOGO_DEV_PUBLISHABLE_KEY, BRANDFETCH_SECRET_API_KEY, SCANNER_API_TOKEN
OPENROUTER_API_KEY, OPENROUTER_MODEL
```
