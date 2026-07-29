"use client"

import { useMemo, useState } from "react"
import { Search, SearchX } from "lucide-react"

import { JobCard } from "@/components/job-card"
import { cn, formatWindow } from "@/lib/utils"
import type { Job } from "@/lib/types"

type SortKey = "newest" | "company"

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
  onView,
}: ResultsProps) {
  const [query, setQuery] = useState("")
  const [sort, setSort] = useState<SortKey>("newest")
  const [hideBlocked, setHideBlocked] = useState(false)

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()

    let list = jobs

    if (needle) {
      list = list.filter(
        (job) =>
          job.title.toLowerCase().includes(needle) ||
          job.company.toLowerCase().includes(needle) ||
          job.location.toLowerCase().includes(needle),
      )
    }

    if (hideBlocked) {
      list = list.filter((job) => job.analysis?.opt_eligible !== "NO")
    }

    return [...list].sort((a, b) =>
      sort === "newest"
        ? (a.age_hours ?? Infinity) - (b.age_hours ?? Infinity)
        : a.company.localeCompare(b.company),
    )
  }, [jobs, query, sort, hideBlocked])

  if (jobs.length === 0) {
    return (
      <section className="rounded-[var(--radius-card)] border border-dashed border-line bg-surface/40 px-6 py-16 text-center">
        <SearchX className="mx-auto size-8 text-faint" />
        <h2 className="mt-4 text-lg font-medium">No results yet</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-faint">
          Pick a timeframe above and hit <span className="text-muted">Run scan</span>{" "}
          to sweep every job board for postings from the last{" "}
          {formatWindow(lookbackHours)}.
        </p>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-5">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">
            {visible.length.toLocaleString()}{" "}
            {visible.length === 1 ? "role" : "roles"}
          </h2>
          <p className="mt-0.5 text-xs text-faint">
            {source === "snapshot" ? (
              <span className="text-warn">
                Packaged snapshot — not a live scan. Run one for fresh results.
              </span>
            ) : (
              <>From the last {formatWindow(lookbackHours)}</>
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter roles…"
              aria-label="Filter roles"
              className={cn(
                "w-full rounded-lg border border-line-soft bg-surface-2/50 py-2 pl-9 pr-3 text-sm sm:w-52",
                "placeholder:text-faint",
                "focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent",
              )}
            />
          </div>

          <button
            type="button"
            onClick={() => setHideBlocked((value) => !value)}
            aria-pressed={hideBlocked}
            className={cn(
              "rounded-lg border px-3 py-2 text-xs transition-colors",
              hideBlocked
                ? "border-accent bg-accent/10 text-accent"
                : "border-line-soft bg-surface-2/50 text-muted hover:text-text",
            )}
          >
            OPT-friendly only
          </button>

          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as SortKey)}
            aria-label="Sort results"
            className="rounded-lg border border-line-soft bg-surface-2/50 px-3 py-2 text-xs text-muted focus:border-accent focus:outline-none"
          >
            <option value="newest">Newest first</option>
            <option value="company">By company</option>
          </select>
        </div>
      </header>

      {visible.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line bg-surface/40 px-4 py-10 text-center text-sm text-faint">
          Nothing matches that filter.
        </p>
      ) : (
        <div className="grid gap-3">
          {visible.map((job) => (
            <JobCard key={job.uid} job={job} onView={onView} />
          ))}
        </div>
      )}
    </section>
  )
}
