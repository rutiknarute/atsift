# Preserved data + ATS endpoints

Reference for the rebuild. The adapters themselves were deleted; these are the
facts they encoded.

## Company catalogs

Scan catalogs are `name,ats,slug` (plus optional `source_url`) with a header
row. The rich reference ledger deliberately retains its original ten-column
schema.

| File | Rows | Contents |
|---|---|---|
| `data/companies_core_ats.csv` | 19,360 | the original six reusable ATS platforms: greenhouse 5,753 · workable 3,479 · ashby 3,313 · smartrecruiters 2,379 · lever 2,263 · rippling 2,173 |
| `data/companies_enterprise_ats.csv` | 6,793 | larger enterprise multi-tenant platforms: icims 5,685 · workday 1,101 · oracle 3 · jibe 2 · avature 1 · successfactors 1 |
| `data/companies_direct.csv` | 3 | company-owned career sites: Apple Careers, IBM Careers, and Atlassian's direct listings feed |
| `data/companies_icims.csv` | 5,685 | production iCIMS portal hosts selected from 5,714 live-verified portals; 29 unmistakable OLD/test portals are excluded from active scanning |
| `data/icims_boards_reference.csv` | 5,714 | rich live-board ledger: employer name, portal and final URLs, iCIMS customer/organization/tenant IDs, company key, job sample count, first-page U.S. evidence, and production eligibility |
| `data/icims_discovery_audit.csv` | 11,739 | every archive/recent-crawl candidate with live acceptance, HTTP result, iCIMS identifiers, and error reason |
| `data/companies_priority.csv` | 154 source rows / 130 unique boards | every supplied career URL in original order, including repeated links; runtime deduplication produces greenhouse 63 · ashby 40 · workday 13 · oracle 3 · jibe 2 · lever 2 · seven other specialized boards |
| `data/job_boards_reference.csv` | 77 | verbatim rich source ledger: company, discovered ATS, token/site, host, board/API URLs, HTTP method, status, and notes |
| `data/companies_reference.csv` | 77 | scan-ready normalization of every rich-reference row across greenhouse 47 · ashby 16 · workday 7 · oracle 3 · lever 2 · avature 1 · jibe 1 |
| `data/companies_plus.csv` | 270 | hidden review ledger, mostly boards that don't resolve or have no adapter (greenhouse 136 · unknown 56 · ashby 54 · workday 10 · lever 9 · comeet 4 · rippling 1) |
| `data/companies.csv` · `data/companies_rippling.csv` · `data/companies_workday.csv` · `data/companies_icims.csv` | 26,156 combined | verified source partitions retained for provenance and repeatable consolidation, not separately selectable scan datasets |
| `data/all_companies.csv` | — | earlier unverified superset, pre-dedup |

`companies_core_ats.csv`, `companies_enterprise_ats.csv`, and
`companies_direct.csv` are the authoritative active scan catalogs. Their
26,156-board union exactly matches the deduplicated union of the four
verified source partitions. The Rippling source partition additionally
requires a distinct public company name, a live v2 jobs payload, and a
canonical public board URL. Don't re-derive active catalogs from
`all_companies.csv`; rebuild them with
`scripts/consolidate_company_datasets.py`. `companies_plus.csv` is not held to
the same verification bar and is not offered in the scan selector.

Which catalog a company lands in is decided by its board, not by hand —
`scanner.companies.dataset_for_ats` is the single rule. The original six
reusable platforms — Ashby, Greenhouse, Lever, Rippling, SmartRecruiters, and
Workable — use `companies_core_ats.csv`. Larger enterprise multi-tenant
platforms — Workday, iCIMS, Oracle, Avature, SuccessFactors, and Jibe — use
`companies_enterprise_ats.csv`. Dedicated Apple and IBM adapters plus
Atlassian's direct listings feed use `companies_direct.csv`.
`scripts/import_companies.py` applies the same rule when merging a new list.
Run that importer with `--verify` and a row whose named board does not answer
is parked in `companies_plus.csv`, keeping the ATS the source claimed: a
company is filed where the list said it was or filed as unresolved, never
quietly moved onto whichever board happens to reply.

`companies_priority.csv` is intentionally different: it preserves every
submitted source URL in a fourth `source_url` column. The scanner still
deduplicates by ATS + slug, so repeated URLs and multiple career/detail links
for the same board remain provenance without scanning that board twice.
Custom career pages are mapped to the public source they actually use. The
specialized mappings include AMD → Jibe, Atlassian → its consolidated direct
feed, IBM → IBM scoped search, Apple → Apple Careers, SAP → SuccessFactors,
Lenovo → Avature, and Dell/JPMorgan Chase/HDFC Bank → Oracle Recruiting,
and custom pages such as Brex, Datadog, HubSpot, Wiz, Zipline, and Databricks
→ their verified Greenhouse tokens.

`job_boards_reference.csv` is also preserved rather than treated as a list of
literal production slugs. Several rows are discovery hints: CareerPuck,
Phenom, and Radancy are wrappers around canonical ATS sources; Oracle requires
the real `CX_*` site number; and the candidate DigitalOcean, Guild, TRM Labs,
and Zipline Greenhouse tokens return 404. HubSpot's candidate token answers
with an empty board. `scripts/normalize_job_boards.py` applies the verified
replacements and generates `companies_reference.csv`, which is available as a
standalone 77-board dataset in the scanner.

`slug` meaning differs by ATS:

- **greenhouse / ashby / lever / rippling / smartrecruiters / workable** — a board token,
  e.g. `0g`, substituted into the endpoint below.
- **icims** — the public portal host, e.g. `careers-acme.icims.com`.
- **avature / jibe / oracle / successfactors / workday** — a full board or API URL. For
  example, Jibe stores `https://careers.amd.com` and Workday stores
  `https://23andme.wd5.myworkdayjobs.com/23`. Workday tenants have no uniform
  short token, but they still belong to the consolidated external ATS dataset.
- **apple / atlassian / ibm** — fixed identifiers or endpoints for dedicated public APIs.

## Endpoints

```
Greenhouse       https://boards-api.greenhouse.io/
Ashby            https://api.ashbyhq.com/
Lever            https://api.lever.co/v0/postings      (EU: https://api.eu.lever.co/v0/postings)
SmartRecruiters  https://api.smartrecruiters.com/v1/companies/
Workable         https://www.workable.com/api/accounts/
Rippling         https://ats.rippling.com/api/v2/board/
Workday          per-tenant board URL from the slug column
Jibe             {career-site origin}/api/jobs
iCIMS            https://{portal}.icims.com/jobs/search?in_iframe=1
Atlassian        https://www.atlassian.com/endpoint/careers/listings
IBM              https://www-api.ibm.com/search/api/v1/ibmcom/appid/careers/
Apple            https://jobs.apple.com/api/v1/search
SuccessFactors   {career-site origin}/search/
Avature          {portal root}/SearchJobs
Oracle Recruiting {site API origin}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
```

All are public, unauthenticated job-board APIs. Lever has a separate EU host.
Ashby boards that disable the posting API fall back to their server-rendered
public board and job pages; this is required for Whatnot and retains the full
description, locations, teams, compensation, and JSON-LD posting date.
Rippling's list payload omits posting dates and descriptions, so the scanner
hydrates only titles that pass the Boolean search. This preserves accurate
freshness filtering without multiplying detail requests across every role on
all 2,173 boards. `scripts/discover_rippling_companies.py` rebuilds the
Rippling catalog from public indexes and refuses to write fewer than 2,000
distinct live companies. SAP's SuccessFactors list likewise needs selective
detail hydration for `datePosted` and the full description. Apple requires a
short-lived CSRF token before its public search request; the adapter reuses
the same HTTP session and stops once its newest-first results exceed the
scanner's 72-hour ceiling.

iCIMS discovery uses archived public search/intro URLs as candidates, then
requires a live 200 response carrying iCIMS customer, organization, or tenant
headers. `scripts/discover_icims_companies.py` refuses to write fewer than
5,000 production portals, preserves all rejected candidates in an audit, and
marks first-page U.S. evidence separately. List cards provide titles and
locations; only title matches are hydrated from JobPosting JSON-LD for the
authoritative posting date, full description, structured location, category,
compensation, and canonical URL.

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
