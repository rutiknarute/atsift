<div align="center">

<img src="web/src/assets/atsift-logo.png" alt="ATSift" width="300">

**Pick a timeframe. Hit run. Get the jobs that are still worth applying to.**

A job-board scanner that sweeps 18,264 company career pages, keeps only the
roles posted inside the window you chose, and tells you before you click
whether the job is actually US-based and whether it will take an F-1/OPT
candidate.

### 🔗 [**atsift.vercel.app**](https://atsift.vercel.app)

<sub>The live link runs in snapshot mode — a packaged sample of 491 real
postings, so you can use the whole interface without a scanner behind it.
[Why](#about-the-deployment).</sub>

</div>

---

## Why I built this

I'm on an F-1 visa. That means two questions decide whether an application is
worth my evening, and job boards answer neither of them:

1. **Is this role actually in the US?** "Remote" shows up on a posting that
   turns out to be Remote–Poland.
2. **Will they sponsor, or at least take OPT?** Most postings don't say. The
   ones that do bury it in the last paragraph, or in a checkbox you only reach
   after twenty minutes of filling in your work history.

And there's a third thing nobody tells you: **timing**. A posting that's three
days old has hundreds of applicants ahead of you. Recruiters work the pile
top-down and stop. If you're not early, you're not really applying — you're
just filing.

So my actual routine was: open twenty career pages I'd bookmarked, scroll each
one, open the promising ones in tabs, read the fine print, close most of them.
Forty-five minutes to find maybe two jobs worth the effort. Every single day.
That's the thing I wanted to delete.

## Why not just use LinkedIn

I tried. Here's where the big boards fall down for this specific problem:

| | LinkedIn / Indeed | ATSift |
|---|---|---|
| **How fresh?** | "Past 24 hours" is a filter on a stale index. Reposts and ghost jobs sit at the top. | The window *is* the scan. It reads the boards live and only keeps what was posted inside 1–72 hours. |
| **Where's the job really?** | Whatever the recruiter typed. "Remote" means nothing. | Every posting gets a location screen, and the ambiguous ones go to a model that reads the description. |
| **Will it take OPT?** | Not a filter that exists. You find out at the end of the form. | Citizenship / clearance / green-card / no-sponsorship clauses are pulled out of the text and shown as one red line on the card. |
| **Coverage** | Only what companies chose to syndicate — and plenty don't. | Goes straight to the source: 18,264 Greenhouse, Ashby, Lever, SmartRecruiters, Workable and Workday boards. |
| **Seniority noise** | "Entry level" returns roles asking for 8 years. | Senior / staff / principal / lead / manager / director titles are excluded before anything is even read, and the years-of-experience line is extracted so you can filter on it. |

The honest summary: the big boards are a **search engine over an index**.
ATSift is a **crawler over the actual ATS APIs**. That's why it can promise
freshness — there's no index in between to go stale.

## The project, in STAR

**Situation** — Job hunting on an F-1 visa, where being late to a posting and
being ineligible for it are the two ways to waste an evening. Existing boards
solve neither. Manually checking career pages worked but cost about 45 minutes
a day and still missed things, because I could only realistically keep an eye
on twenty or so companies.

**Task** — Build something that answers "what went up recently, is in the US,
and will take me?" across thousands of companies instead of twenty — fast
enough to run before work, and cheap enough that I'd actually keep running it.

**Action** —
- Built a Python scanner with one adapter per ATS (six of them), reading the
  same public JSON endpoints the companies' own career pages use.
- Assembled and cleaned a catalog of **18,283 boards** — deduplicated by
  ATS + slug and live-checked that each one resolves to a real US posting.
- Wrote a boolean title filter (category keywords AND NOT seniority terms) so
  the expensive steps never see a role I couldn't take anyway.
- Ran per-job screening on a **local Llama 3.2 3B through Ollama**, because
  this is thousands of calls per scan and a hosted API would have made the
  whole idea unaffordable. More on that below.
- Rebuilt the pipeline so each posting runs end-to-end on its own and appears
  the moment it clears, instead of the UI sitting on a spinner until the whole
  catalog finished.
- Added a conversational agent over the results, so I can ask "React roles
  under 2 years that don't block OPT" instead of driving filter dropdowns.

**Result** — A scan of the full Workday catalog — **1,097 boards, 12-hour
window** — completed in **42 minutes**, surfacing **160 postings**, of which
**124** cleared US-location and eligibility screening. The daily 45 minutes of
manual clicking is gone; I read a list instead. And because screening runs
locally, a scan of that size costs **$0 in inference**.

> Workday is the slowest of the six — it's a paged POST API, one request per
> 20 jobs. The other five are considerably quicker per board.

## How a scan actually works

The important design decision is that **every posting runs the whole pipeline
on its own**. Nothing waits for the catalog to finish.

```
fetch board → title match → time window → location screen → fetch JD → LLM → listed
   18,264      keywords,      6–72h        regex, free      only for   only for
   boards      minus senior                                 survivors  survivors
```

Each step only sees what survived the previous one. That ordering is the whole
reason this is affordable: by the time a posting reaches the language model,
thousands of others have already been eliminated for free by string matching.

The first version did this in phases — sweep everything, then screen
everything, then read everything. It worked, but you stared at a progress bar
for the entire scan and got all the results in one dump at the end. Now the
board sweep and the screening overlap: results start appearing seconds in and
the list grows while the scan is still running. Same total work, completely
different to actually use.

## The two-model split

This is the part I'd most want to talk through in an interview.

**Bulk screening runs locally on `llama3.2:3b` via Ollama.** A scan puts
hundreds to thousands of job descriptions through a model. At hosted per-token
prices that's a real bill every single morning, for a tool I built to use
daily. A 3B model running on my own machine is slower per call and not as
sharp — but it's free, it's private, and latency genuinely doesn't matter when
the work is already happening in the background. Analyses are cached by a
fingerprint of prompt version + model + job fields, so re-scans don't re-pay
for work already done.

**The conversational Scout runs on a hosted model** (Llama 3.3 70B via
OpenRouter). Opposite trade: it's one call, you're waiting on it, and quality
is the entire point. Paying per token is completely fine when there's a human
watching the cursor blink.

I also don't trust either model further than I have to. Anything that can be
decided deterministically is: the years-of-experience label and the
eligibility blockers are regex and rules over the posting's own words, layered
on top of the model output rather than taken from it. The model fills gaps; it
doesn't get the final say.

## The AI Job Scout

There's a chat agent in the bottom-right corner. It only ever answers from
roles the current scan actually found — it can't invent a job.

Ask it things like:

- *"Entry-level React roles from the last day"*
- *"Data analyst jobs that don't block OPT"*
- *"AI/ML roles needing under 2 years"*

It answers in plain English and links straight to the posting. It exists
because filter dropdowns are fine when you know exactly what you want, and
useless when what you want is "something like the last one, but less senior".

## What you get per role

Each result card shows what I'd otherwise have to open the posting to learn:

- **Required experience**, condensed — `5+ years`, `1–2 years`, `Not listed` —
  pulled out of the description rather than the title
- **A red one-liner if the posting rules you out**, e.g. *Requires US
  citizenship — closed to F-1/OPT*, or a security-clearance requirement
- **When it was first published**, and how long ago
- **Where it actually is**, after the location screen
- **Q&A and Summary** panels — degree, qualifications, salary if listed, key
  tech, the ATS keywords worth mirroring in your résumé
- **Apply now**, which flips to **Already Applied** with a tick once clicked,
  so you don't open the same job twice next morning

## Stack

**Scanner** — Python 3.13, Flask, `ThreadPoolExecutor` for the board sweep,
a single-consumer queue for screening (the local model is one resource), Ollama
+ `llama3.2:3b`.

**Dashboard** — Next.js 16 (App Router, Turbopack), React 19, TypeScript,
Tailwind CSS v4, Vercel AI SDK for the streaming chat.

**Auth** — one account. Password stored only as an scrypt hash, session in a
signed HTTP-only cookie, gated by `proxy.ts` (Next 16's replacement for
`middleware.ts`). Anyone else who lands on the login page can request access,
which emails me through Resend.

**Tests** — 60 backend tests covering the boolean search, the date window, each
ATS adapter, location screening, experience extraction, and the incremental
publishing behaviour.

## Running it yourself

### 1. The scanner

```bash
python3 -m pip install -r requirements.txt
ollama pull llama3.2:3b
python3 app.py                 # http://127.0.0.1:5057
```

> Port 5057 and not Flask's usual 5000 on purpose: on macOS, AirPlay Receiver
> binds 5000 and answers `403`, which looks *exactly* like a dead scanner to
> the dashboard's health probe. That one cost me an embarrassing amount of
> debugging.

**Restart the scanner after changing anything under `scanner/`.** Python
imports a module once, so an edited adapter keeps running its old code until
the process comes back — and the only symptom is wrong output, which looks
identical to a bug in the new code. `GET /api/health` reports `stale: true`
when the source on disk is newer than the running process:

```bash
curl -s localhost:5057/api/health | grep -o '"stale":[a-z]*'
```

### 2. The dashboard

```bash
cd web
npm install
npm run dev                    # http://localhost:3000
```

`web/.env.local`:

```
SCANNER_API_BASE_URL=http://127.0.0.1:5057
SCANNER_API_TOKEN=<same value as the scanner's>
OPENROUTER_API_KEY=<key>
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
LOGO_DEV_PUBLISHABLE_KEY=<public Logo.dev key>

AUTH_EMAIL=<the one account>
AUTH_PASSWORD_HASH=scrypt:16384:8:1:<salt>:<hash>
AUTH_SECRET=<32 random bytes, base64url>
RESEND_API_KEY=<Resend key>
AUTH_EMAIL_FROM=ATSift <onboarding@resend.dev>
```

Generate a password hash with:

```bash
node -e "const{scryptSync,randomBytes}=require('node:crypto');const s=randomBytes(16);console.log(['scrypt',16384,8,1,s.toString('base64url'),scryptSync(process.argv[1],s,64,{N:16384,r:8,p:1}).toString('base64url')].join(':'))" 'YOUR_PASSWORD'
```

Colons rather than the conventional `$` separators, because dotenv expands
`$name` inside `.env` values and quietly ate half my hash the first time.

## About the deployment

**Only `web/` is deployed.** The scanner can't go serverless — it's
long-running and stateful, holds a cancel event in memory, streams progress,
and needs Ollama resident on the machine. A serverless function that dies after
60 seconds can't sweep 18,000 boards.

So the live link runs in **snapshot mode**: it serves a packaged sample of 491
real postings from an earlier scan, so you can see and use the whole interface
— filters, cards, eligibility flags, the Scout — without a Python process
behind it. Run a live scan by starting the scanner locally, as above.

If you want to see a scan actually run, there's a
**[second deployment](https://beone-theta.vercel.app/)** whose screening is
wired to a hosted Llama model instead of a local one — no Ollama to keep
resident, so it can scan on demand. It's linked from the login page too.

The dashboard decides this with a health probe rather than by whether a URL is
configured, because a URL that merely parses is not a reachable scanner.

## Things I'd do next

- Push the scanner onto a small always-on box so scans can be scheduled instead
  of triggered, with a morning digest.
- Replace the snapshot on the live demo with a read-only feed from that box.
- Widen the catalog past the six ATS platforms — Taleo and iCIMS are the
  obvious gaps.
- Let the Scout act, not just answer: "track this company" and have the next
  scan prioritise it.

## Repo layout

```
├── app.py                  Entry point
├── scanner/
│   ├── boolean_search.py   ← the filter that defines the product
│   ├── ats/                One adapter per board, plus dispatch
│   ├── scan.py             The sweep and the per-posting pipeline
│   ├── analysis.py         Ollama screening, cached by fingerprint
│   ├── locations.py        US screening
│   ├── experience.py       Deterministic experience extraction
│   └── web.py              Flask routes
├── data/                   Company catalogs and the packaged sample
├── tests/                  60 backend tests
└── web/                    Next.js 16 dashboard
```

## API

| Route | |
|---|---|
| `GET /api/health` | Liveness; no token required |
| `GET /api/meta` | Categories, catalogs, timeframe options |
| `GET /api/status` | Live scan progress |
| `GET /api/jobs?lookback_hours=24` | Stored results |
| `POST /api/scan` | `{lookback_hours, dataset, categories}` |
| `POST /api/scan/stop` | Cancel a running scan |

`/api/*` requires `Authorization: Bearer $SCANNER_API_TOKEN` whenever it's set.
Leave it unset only on `127.0.0.1`.

## Data

| File | |
|---|---|
| `data/companies.csv` | 17,189 companies — greenhouse 5,753 · workable 3,480 · ashby 3,312 · smartrecruiters 2,381 · lever 2,263 |
| `data/companies_workday.csv` | 1,097 Workday tenants, kept separate because the slug is a full board URL |
| `data/companies_plus.csv` | 271 companies — mostly boards no adapter reads or whose named slug didn't resolve, parked rather than dropped, plus a handful of hand-verified extras not yet folded into `companies.csv` |

Every company was deduplicated by ATS + slug and live-checked for a resolvable
US posting before being kept.

---

<div align="center">
<sub>Built by <a href="https://github.com/rutiknarute">Rutik Narute</a> — because forty-five minutes a day is a lot of minutes.</sub>
</div>
