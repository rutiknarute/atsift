# Boolean search — the filter that defines the product

This is the keyword logic the rebuild must reimplement. It decides what counts
as a relevant posting, so it is the one piece of the old scanner that is
product, not plumbing.

## The rule

A posting is kept for a category when:

```
include_pattern matches the title  AND  exclude_pattern does NOT match the title
```

A title may match several categories at once — the old implementation returned
*every* matched category, it did not stop at the first.

## Boundary-safe matching

Keywords are matched with a word-boundary guard, not a plain substring test.
This is not cosmetic — plain `in` matching produced real false positives:

| Keyword | Must NOT match |
|---|---|
| `UI` | b**ui**ld |
| `sr` | **SR**E |
| `lead` | **lead**erboard |
| `MS` | for**ms**, tea**ms** |
| `grad` | up**grad**e |

The pattern used, with keywords sorted longest-first so the longest alternative
wins before a shorter prefix can claim the match:

```python
re.compile(r"(?<!\w)(?:" + "|".join(escaped) + r")(?!\w)", re.IGNORECASE)
```

`(?<!\w)` / `(?!\w)` rather than `\b` — `\b` behaves badly around keywords that
start or end with a non-word character.

## Exclude lists

Applied *after* the include match. Two variants.

**Standard** — used by every category except GTM:

```
senior, sr, lead, staff, manager, principal, director,
vp, vice president, embedded, phd, head, architect
```

**GTM** — drops `architect`, adds `recruiter`:

```
senior, sr, lead, staff, manager, principal, director,
vp, vice president, embedded, phd, head, recruiter
```

## Categories

### `software` → "Software"
```
software, AI software, application developer, SDE, full stack, frontend,
front end, backend, back end, web developer, UI, full-stack,
platform engineer, SWE, product engineer, associate developer,
application, python, university
```

### `new_grad` → "New Grad"
```
new grad, new graduate, recent graduate, recent grad, college graduate,
entry level, entry-level, early career, early careers, university graduate,
graduate program, graduate role, graduate, early talent, grad, MS, Co-op,
masters
```

### `data_analyst` → "Data Analyst"
```
data analyst, data analytics, AI data, business analyst, business data,
business intelligence, BI analyst, reporting analyst, data reporting,
analytics analyst, insights analyst, data insights analyst, product analyst,
operations analyst, quantitative analyst, data quality analyst,
data governance, data visualization, dashboard analyst, SQL, Excel, tableau,
power BI, analytics consultant, data consultant
```

### `data_engineer` → "Data Engineer"
```
data engineer, data engineering, data developer, data pipeline, big data,
ETL, ELT, data integration, data warehouse, informatica, data migration,
data platform, analytics engineer, data ingestion, Junior Data,
Associate Data, data operations, Cloud Data, database developer, Snowflake,
data lake
```

### `ai_ml` → "AI / ML"
```
AI Engineer, AI/ML, GenAI, Applied Scientist, LLM, Gen AI, Generative AI,
Forward Deployed, Forward-Deployed, FDE, fine tuning, Applied Science,
Visual Data, Data Annotator, Data Labeling, AI Trainer, RLHF Specialist,
Training Data, Annotation Analyst, AI Data, Data Quality, Data Labeler,
Data Annotation
```

### `gtm` → "GTM"
```
GTM, Go-To-Market, Growth, RevOps Engineer, Founding, AI Automation,
AI Workflow, Prompt Engineer, AI Product, AI Solutions, AI Operations,
Marketing Operations, Product Growth, Product Operations, Claude,
Marketing Technology, Codex, Automation Engineer, Workflow Automation, RAG,
Prompt Engineering
```

## Notes for the rebuild

- Compile the include and exclude patterns **once** at module load, not per
  title. The old code built a `{category: (include, exclude)}` map up front and
  reused it across the whole sweep — titles are checked tens of thousands of
  times per scan.
- Keep the keyword lists as plain data, separate from the matching code, so
  they can be tuned without touching logic.
- `AI Data` and `Data Quality` appear in both `data_analyst` and `ai_ml`. That
  overlap is intentional — multi-category matching is a feature.
