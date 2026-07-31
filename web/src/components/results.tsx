"use client"

import { useMemo, useState } from "react"
import { CheckCircle2, ChevronDown, Search, SearchX } from "lucide-react"

import { JobCard } from "@/components/job-card"
import { cn, formatWindow } from "@/lib/utils"
import type { CategoryId, Job } from "@/lib/types"

type SortKey = "newest" | "company"
type ExperienceKey = "all" | "max1" | "max2" | "max3" | "min3"

/*
  Filters on the years a posting actually requires. Every band but the last is
  a ceiling, so they nest rather than partition — a 2-year role shows under
  "2 years or less" and under "3 years or less" both.
*/
const EXPERIENCE_FILTERS: {
  id: ExperienceKey
  label: string
  match: (years: number) => boolean
}[] = [
  { id: "all", label: "Any experience", match: () => true },
  { id: "max1", label: "1 year or less", match: (years) => years <= 1 },
  { id: "max2", label: "2 years or less", match: (years) => years <= 2 },
  { id: "max3", label: "3 years or less", match: (years) => years <= 3 },
  { id: "min3", label: "3+ years", match: (years) => years >= 3 },
]

const ROLE_FILTERS: { id: CategoryId | "all"; label: string }[] = [
  { id: "all", label: "All roles" },
  { id: "software", label: "Software" },
  { id: "new_grad", label: "New Grad" },
  { id: "data_analyst", label: "Data Analyst" },
  { id: "data_engineer", label: "Data Engineer" },
  { id: "ai_ml", label: "AI / ML" },
  { id: "gtm", label: "GTM" },
]

interface ResultsProps {
  jobs: Job[]
  source: "scanner" | "snapshot"
  lookbackHours: number
  scannedAt: string | null
  loading: boolean
  onApply: (uid: string) => void
}

export function Results({
  jobs,
  source,
  lookbackHours,
  scannedAt,
  loading,
  onApply,
}: ResultsProps) {
  const [query, setQuery] = useState("")
  const [role, setRole] = useState<CategoryId | "all">("all")
  const [sort, setSort] = useState<SortKey>("newest")
  const [experience, setExperience] = useState<ExperienceKey>("all")
  const [optOnly, setOptOnly] = useState(false)

  const counts = useMemo(() => {
    const map = new Map<string, number>()

    for (const job of jobs) {
      for (const category of job.categories ?? []) {
        map.set(category, (map.get(category) ?? 0) + 1)
      }
    }

    return map
  }, [jobs])

  const filteredJobs = useMemo(() => {
    const needle = query.trim().toLowerCase()

    let list = jobs

    if (role !== "all") {
      list = list.filter((job) => (job.categories ?? []).includes(role))
    }

    if (needle) {
      list = list.filter(
        (job) =>
          job.title.toLowerCase().includes(needle) ||
          job.company.toLowerCase().includes(needle) ||
          (job.location ?? "").toLowerCase().includes(needle) ||
          (job.analysis?.key_tech_skills ?? []).some((skill) =>
            skill.toLowerCase().includes(needle),
          ),
      )
    }

    if (optOnly) {
      list = list.filter((job) => job.analysis?.opt_eligible === "YES")
    }

    if (experience !== "all") {
      const band = EXPERIENCE_FILTERS.find((item) => item.id === experience)

      // A posting whose requirement could not be read is left out of every
      // band rather than guessed into one — its tile says "Not listed", and
      // that is not the same as qualifying.
      list = list.filter((job) => {
        const years = job.analysis?.minimum_years

        return typeof years === "number" && (band?.match(years) ?? true)
      })
    }

    return [...list].sort((a, b) =>
      sort === "newest"
        ? (a.age_hours ?? Infinity) - (b.age_hours ?? Infinity)
        : a.company.localeCompare(b.company),
    )
  }, [jobs, query, role, sort, optOnly, experience])

  function clearFilters() {
    setQuery("")
    setRole("all")
    setOptOnly(false)
    setSort("newest")
    setExperience("all")
  }

  if (loading && jobs.length === 0) {
    return <ResultsSkeleton />
  }

  if (jobs.length === 0) {
    return (
      <section className="rounded-[var(--radius-card)] border border-dashed border-line bg-surface/70 px-6 py-14 text-center">
        <SearchX aria-hidden="true" className="mx-auto size-7 text-faint" />
        <h2 className="mt-4 font-display text-lg font-bold">No roles found</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">
          {source === "scanner"
            ? `Try a wider time window, then run another scan. The current window is ${formatWindow(lookbackHours)}.`
            : "The packaged sample is unavailable. Reconnect the scanner and try again."}
        </p>
      </section>
    )
  }

  return (
    <section aria-labelledby="results-heading" className="flex flex-col gap-4">
      <h2
        id="results-heading"
        aria-live="polite"
        className="font-display text-2xl font-bold tracking-tight text-text"
      >
        {filteredJobs.length.toLocaleString()} matching{" "}
        {filteredJobs.length === 1 ? "role" : "roles"}
      </h2>

      {/*
        One toolbar, no captions: a search field, a check toggle, and a sort
        dropdown each say what they do through their own placeholder, label, or
        selected value. The captions above them were saying it a second time.
      */}
      <div className="rounded-[var(--radius-card)] border border-line bg-surface p-3 sm:p-4">
        <div className="grid gap-2.5 lg:grid-cols-[minmax(12rem,1fr)_auto_auto_auto] lg:items-center">
          <span className="relative block min-w-0">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint"
            />
            <input
              type="search"
              name="job-search"
              autoComplete="off"
              aria-label="Search roles, companies, and skills"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search roles, companies, skills…"
              className={cn(
                "min-h-11 w-full rounded-xl border border-line bg-surface-2 pl-10 pr-3 text-sm",
                "placeholder:text-faint",
                "focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/25",
              )}
            />
          </span>

          <button
            type="button"
            onClick={() => setOptOnly((value) => !value)}
            aria-pressed={optOnly}
            className={cn(
              "inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border px-4 text-sm font-medium transition-colors lg:w-auto",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
              optOnly
                ? "border-brand-line bg-brand-soft text-brand-deep"
                : "border-line bg-surface-2 text-muted hover:border-faint hover:text-text",
            )}
          >
            <CheckCircle2 aria-hidden="true" className="size-4" />
            OPT eligible only
          </button>

          <span className="relative block">
            <select
              name="job-experience"
              aria-label="Filter by required experience"
              value={experience}
              onChange={(event) =>
                setExperience(event.target.value as ExperienceKey)
              }
              className={cn(
                "min-h-11 w-full appearance-none rounded-xl border pl-3.5 pr-10 text-sm transition-colors lg:w-44",
                "focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/25",
                experience === "all"
                  ? "border-line bg-surface-2 text-muted hover:border-faint"
                  : "border-brand-line bg-brand-soft font-medium text-brand-deep",
              )}
            >
              {EXPERIENCE_FILTERS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
            <ChevronDown
              aria-hidden="true"
              className={cn(
                "pointer-events-none absolute right-3.5 top-1/2 size-4 -translate-y-1/2",
                experience === "all" ? "text-faint" : "text-brand-deep",
              )}
            />
          </span>

          <span className="relative block">
            <select
              name="job-sort"
              aria-label="Sort results"
              value={sort}
              onChange={(event) => setSort(event.target.value as SortKey)}
              className="min-h-11 w-full appearance-none rounded-xl border border-line bg-surface-2 pl-3.5 pr-10 text-sm text-muted transition-colors hover:border-faint focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/25 lg:w-40"
            >
              <option value="newest">Newest first</option>
              <option value="company">Company A–Z</option>
            </select>
            <ChevronDown
              aria-hidden="true"
              className="pointer-events-none absolute right-3.5 top-1/2 size-4 -translate-y-1/2 text-faint"
            />
          </span>
        </div>

        <div className="mt-3 border-t border-line-soft pt-3">
          <div
            aria-label="Filter by role type"
            className={cn(
              "-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1",
              "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
            )}
          >
            {ROLE_FILTERS.map((filter) => {
              const active = role === filter.id
              const count =
                filter.id === "all" ? jobs.length : (counts.get(filter.id) ?? 0)

              if (filter.id !== "all" && count === 0) return null

              return (
                <button
                  key={filter.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setRole(filter.id)}
                  className={cn(
                    "min-h-11 shrink-0 whitespace-nowrap rounded-lg border px-3 text-xs font-medium transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
                    active
                      ? "border-brand bg-brand text-brand-ink"
                      : "border-line bg-surface text-muted hover:border-faint hover:text-text",
                  )}
                >
                  {filter.label}
                  <span className="ml-1.5 font-mono tabular-nums opacity-70">
                    {count.toLocaleString()}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {filteredJobs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line bg-surface/70 px-4 py-10 text-center">
          <SearchX aria-hidden="true" className="mx-auto size-6 text-faint" />
          <p className="mt-3 text-sm font-semibold">No matching roles</p>
          <p className="mt-1 text-sm text-muted">
            Clear the filters or try a broader search.
          </p>
          <button
            type="button"
            onClick={clearFilters}
            className="mt-4 min-h-11 rounded-xl border border-line bg-surface px-4 text-sm font-semibold transition-colors hover:border-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
          >
            Clear filters
          </button>
        </div>
      ) : (
        // Every match renders. The filters above are the way to narrow a long
        // list; a "show more" button only ever hid results behind a click.
        <div className="grid items-start gap-4 lg:grid-cols-2">
          {filteredJobs.map((job) => (
            <JobCard
              key={job.uid}
              job={job}
              lastSeen={scannedAt}
              onApply={onApply}
            />
          ))}
        </div>
      )}
    </section>
  )
}

function ResultsSkeleton() {
  return (
    <section aria-label="Loading job results" aria-busy="true">
      <div className="h-7 w-52 animate-pulse rounded-lg bg-line" />
      <div className="mt-4 h-36 animate-pulse rounded-[var(--radius-card)] border border-line bg-surface" />
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {[0, 1, 2, 3].map((item) => (
          <div
            key={item}
            className="h-64 animate-pulse rounded-[var(--radius-card)] border border-line bg-surface"
          />
        ))}
      </div>
      <span className="sr-only">Loading roles…</span>
    </section>
  )
}
