# The motto

**The user picks a timeframe, hits Run, and the boolean search brings back the
results.**

That sentence is the product. Everything in the rebuild should serve it, and
anything that doesn't get in its way.

## The core loop

```
pick timeframe  →  hit Run  →  live progress  →  results
```

1. **Pick a timeframe.** How far back to look for postings. Must be the most
   prominent control on the page — it is the one input the user actually makes.
2. **Hit Run.** One unmistakable primary action. Not buried in a filter panel.
3. **Watch it work.** A scan sweeps thousands of boards and takes real time.
   Silence reads as broken, so progress has to be visible and the run has to be
   cancellable.
4. **Get results.** Postings inside the window that pass the boolean search,
   each screened for US location and OPT eligibility.

## What the timeframe means

The window is the *product*, not a post-filter. The chosen timeframe drove the
scan itself and the results — a lesson from three separate commits in the old
repo (`Make the chosen time window drive the results, not just the scan`,
`Apply the date-only window rule to the packaged snapshot too`). Don't scan a
fixed horizon and filter afterward; the two must agree, snapshot included.

The old build capped the horizon at 72 hours. Freshness is the point: a
week-old new-grad posting is usually already flooded.

## What gets returned

A posting survives when:

1. Its **title passes the boolean search** — see `boolean-search.md`.
2. It is **inside the chosen window**.
3. It is **US-based** — structured location data first, LLM only for genuinely
   ambiguous city-only locations.
4. It is **OPT-viable** — the LLM answers this and cites the blocking line when
   the answer is no.

Then each result carries: degree requirement, experience/minimum years, key
tech skills, ATS resume keywords, salary if listed, team, and one actionable
tip.

## The two LLM roles

| Where | Model | Job |
|---|---|---|
| Scanner, per posting | Ollama `llama3.2:3b`, local | Screen US location + OPT, extract the fields above. Cached by fingerprint. |
| Dashboard, conversational | OpenRouter `meta-llama/llama-3.3-70b-instruct`, hosted | "AI Job Scout" — plain-English read-only search over already-scanned jobs. |

The local model does bulk per-job work where volume makes API pricing hurt; the
hosted model handles interactive chat where latency and quality matter. Keep
that split.

## Hard-won constraints

Carried forward from the old build — these were each learned the expensive way:

- **The scanner can't be serverless.** Long-running, stateful, holds a cancel
  event in memory, streams progress, needs Ollama resident. It runs locally or
  on a persistent host; only the frontend deploys.
- **Decide "can I scan?" by health probe, not by config.** A configured URL that
  merely parses is not a reachable scanner — that once left production
  advertising a scanner at its own loopback address.
- **Never let a build copy local `.env` files into a deployed bundle.** That
  once shipped a localhost scanner URL and a live API key to production.
- **Protect the scanner when exposed.** Bearer token on `/api/*` whenever it is
  reachable beyond `127.0.0.1`.
- **Degrade to the snapshot.** With no scanner reachable, the UI stays fully
  browsable against the packaged snapshot and hides the Run button rather than
  offering an action that will fail.
