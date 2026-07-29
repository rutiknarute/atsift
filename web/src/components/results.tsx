"use client"

import { useMemo, useState } from "react"
import { Search, SearchX } from "lucide-react"

import { JobCard } from "@/components/job-card"
import { cn, formatWindow } from "@/lib/utils"
import type { CategoryId, Job } from "@/lib/types"

type SortKey = "newest" | "company"

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
  onView: (uid: string) => void
}

export function Results({
  jobs,
  source,
  lookbackHours,
  scannedAt,
  onView,
}: ResultsProps) {
  const [query, setQuery] = useState("")
  const [role, setRole] = useState<CategoryId | "all">("all")
  const [sort, setSort] = useState<SortKey>("newest")
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

  const visible = useMemo(() => {
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
          job.location.toLowerCase().includes(needle) ||
          (job.analysis?.key_tech_skills ?? []).some((skill) =>
            skill.toLowerCase().includes(needle),
          ),
      )
    }

    if (optOnly) {
      list = list.filter((job) => job.analysis?.opt_eligible !== "NO")
    }

    return [...list].sort((a, b) =>
      sort === "newest"
        ? (a.age_hours ?? Infinity) - (b.age_hours ?? Infinity)
        : a.company.localeCompare(b.company),
    )
  }, [jobs, query, role, sort, optOnly])

  if (jobs.length === 0) {
    return (
      <section className="rounded-[var(--radius-card)] border border-dashed border-line bg-surface/40 px-6 py-16 text-center">
        <SearchX className="mx-auto size-8 text-faint" />
        <h2 className="mt-4 text-lg font-medium">No results yet</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-faint">
          Choose a timeframe above and hit{" "}
          <span className="text-muted">Run scan</span> to sweep every job board
          for postings from the last {formatWindow(lookbackHours)}.
        </p>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">
          {visible.length.toLocaleString()}{" "}
          {visible.length === 1 ? "role" : "roles"}
        </h2>

        <p className="text-xs text-faint">
          {source === "snapshot" ? (
            <span className="text-warn">
              Packaged snapshot — not a live scan.
            </span>
          ) : (
            <>From the last {formatWindow(lookbackHours)}</>
          )}
        </p>
      </div>

      {/* Filter row: roles on the left, search on the right. The role chips
          scroll horizontally rather than wrapping, so they never push the
          search box out of line on narrow screens. */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div
          role="tablist"
          aria-label="Filter roles"
          className={cn(
            "-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 lg:pb-0",
            "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
            // Fade the trailing edge so a chip cut off by the scroll reads as
            // "there is more here", not as a broken layout.
            "[mask-image:linear-gradient(to_right,#000_calc(100%-2rem),transparent)]",
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
                role="tab"
                aria-selected={active}
                onClick={() => setRole(filter.id)}
                className={cn(
                  "shrink-0 whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition-colors",
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
                  active
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-line-soft bg-surface-2/50 text-muted hover:text-text",
                )}
              >
                {filter.label}
                <span className="ml-1.5 tabular-nums opacity-60">{count}</span>
              </button>
            )
          })}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <div className="relative flex-1 lg:flex-none">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search title, company, skill…"
              aria-label="Search results"
              className={cn(
                "w-full rounded-lg border border-line-soft bg-surface-2/50 py-2 pl-9 pr-3 text-sm lg:w-64",
                "placeholder:text-faint",
                "focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent",
              )}
            />
          </div>

          <button
            type="button"
            onClick={() => setOptOnly((value) => !value)}
            aria-pressed={optOnly}
            className={cn(
              "shrink-0 rounded-lg border px-3 py-2 text-xs transition-colors",
              optOnly
                ? "border-accent bg-accent/10 text-accent"
                : "border-line-soft bg-surface-2/50 text-muted hover:text-text",
            )}
          >
            OPT ok
          </button>

          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as SortKey)}
            aria-label="Sort results"
            className="shrink-0 rounded-lg border border-line-soft bg-surface-2/50 px-3 py-2 text-xs text-muted focus:border-accent focus:outline-none"
          >
            <option value="newest">Newest</option>
            <option value="company">Company</option>
          </select>
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line bg-surface/40 px-4 py-10 text-center text-sm text-faint">
          Nothing matches that filter.
        </p>
      ) : (
        <div className="grid gap-3">
          {visible.map((job) => (
            <JobCard
              key={job.uid}
              job={job}
              lastSeen={scannedAt}
              onView={onView}
            />
          ))}
        </div>
      )}
    </section>
  )
}
