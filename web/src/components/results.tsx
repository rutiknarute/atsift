"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { CheckCircle2, ChevronDown, Search, SearchX } from "lucide-react"

import { JobCard } from "@/components/job-card"
import { ATS_LABELS } from "@/components/brand"
import { cn, formatWindow } from "@/lib/utils"
import type { CategoryId, Job } from "@/lib/types"

type SortKey = "newest" | "company"
type ExperienceKey = "max1" | "max2" | "max3" | "min3" | "not_listed"

/*
  Filters on the years a posting actually requires. The three ceilings nest
  rather than partition — a 2-year role matches "2 years or less" and "3
  years or less" both. "Not listed" is its own band for postings whose
  requirement couldn't be read at all, rather than folding them into one of
  the others. Checking several bands is an OR: any match includes the job.
*/
const EXPERIENCE_FILTERS: {
  id: ExperienceKey
  label: string
  match: (years: number | null) => boolean
}[] = [
  { id: "max1", label: "1 year or less", match: (years) => years !== null && years <= 1 },
  { id: "max2", label: "2 years or less", match: (years) => years !== null && years <= 2 },
  { id: "max3", label: "3 years or less", match: (years) => years !== null && years <= 3 },
  { id: "min3", label: "3+ years", match: (years) => years !== null && years >= 3 },
  { id: "not_listed", label: "Not listed", match: (years) => years === null },
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
  // Empty set reads as "no filter" rather than "match nothing" for both of
  // these — see `experience.size > 0` and `atsFilter.size > 0` below.
  const [experience, setExperience] = useState<Set<ExperienceKey>>(new Set())
  const [optOnly, setOptOnly] = useState(false)
  const [atsFilter, setAtsFilter] = useState<Set<string>>(new Set())

  const counts = useMemo(() => {
    const map = new Map<string, number>()

    for (const job of jobs) {
      for (const category of job.categories ?? []) {
        map.set(category, (map.get(category) ?? 0) + 1)
      }
    }

    return map
  }, [jobs])

  const experienceOptions = useMemo(
    () =>
      EXPERIENCE_FILTERS.map((band) => ({
        ...band,
        count: jobs.filter((job) =>
          band.match(job.analysis?.minimum_years ?? null),
        ).length,
      })),
    [jobs],
  )

  // Options are built from whatever ATS values are actually present, so the
  // list never offers a platform with zero results to pick from.
  const atsOptions = useMemo(() => {
    const map = new Map<string, number>()

    for (const job of jobs) {
      map.set(job.ats, (map.get(job.ats) ?? 0) + 1)
    }

    return [...map.entries()]
      .map(([id, count]) => ({
        id,
        count,
        label: ATS_LABELS[id] ?? (id || "Unknown ATS"),
      }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
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

    if (atsFilter.size > 0) {
      list = list.filter((job) => atsFilter.has(job.ats))
    }

    if (experience.size > 0) {
      list = list.filter((job) => {
        const years = job.analysis?.minimum_years ?? null

        return EXPERIENCE_FILTERS.some(
          (band) => experience.has(band.id) && band.match(years),
        )
      })
    }

    return [...list].sort((a, b) =>
      sort === "newest"
        ? (a.age_hours ?? Infinity) - (b.age_hours ?? Infinity)
        : a.company.localeCompare(b.company),
    )
  }, [jobs, query, role, sort, optOnly, experience, atsFilter])

  function clearFilters() {
    setQuery("")
    setRole("all")
    setOptOnly(false)
    setSort("newest")
    setExperience(new Set())
    setAtsFilter(new Set())
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
        <div className="grid gap-2.5 lg:grid-cols-[minmax(12rem,1fr)_auto_auto_auto_auto] lg:items-center">
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

          <MultiSelectFilter
            options={experienceOptions}
            selected={experience}
            onChange={setExperience}
            allLabel="Any experience"
            summaryLabel={(n) => `${n} experience filters`}
            groupLabel="Filter by required experience"
          />

          <MultiSelectFilter
            options={atsOptions}
            selected={atsFilter}
            onChange={setAtsFilter}
            allLabel="All ATS"
            summaryLabel={(n) => `${n} ATS selected`}
            groupLabel="Filter by ATS platform"
          />

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

/*
  A button that opens a checklist rather than a native <select multiple>: the
  browser control for that requires a modifier click to pick more than one
  option, which nobody discovers on their own. Shared by the experience and
  ATS filters, which differ only in their option list and labels.
*/
function MultiSelectFilter<T extends string>({
  options,
  selected,
  onChange,
  allLabel,
  summaryLabel,
  groupLabel,
}: {
  options: { id: T; label: string; count?: number }[]
  selected: Set<T>
  onChange: (next: Set<T>) => void
  allLabel: string
  summaryLabel: (count: number) => string
  groupLabel: string
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false)
    }

    document.addEventListener("mousedown", onPointerDown)
    window.addEventListener("keydown", onKeyDown)

    return () => {
      document.removeEventListener("mousedown", onPointerDown)
      window.removeEventListener("keydown", onKeyDown)
    }
  }, [open])

  function toggle(id: T) {
    const next = new Set(selected)

    if (next.has(id)) next.delete(id)
    else next.add(id)

    onChange(next)
  }

  const active = selected.size > 0
  const summary =
    selected.size === 0
      ? allLabel
      : selected.size === 1
        ? (options.find((option) => selected.has(option.id))?.label ??
          summaryLabel(1))
        : summaryLabel(selected.size)

  if (options.length === 0) return null

  return (
    <div ref={containerRef} className="relative block">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="true"
        aria-expanded={open}
        className={cn(
          "flex min-h-11 w-full items-center justify-between gap-2 rounded-xl border px-3.5 text-sm transition-colors lg:w-44",
          "focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/25",
          active
            ? "border-brand-line bg-brand-soft font-medium text-brand-deep"
            : "border-line bg-surface-2 text-muted hover:border-faint",
        )}
      >
        <span className="truncate">{summary}</span>
        <ChevronDown
          aria-hidden="true"
          className={cn(
            "size-4 shrink-0",
            active ? "text-brand-deep" : "text-faint",
          )}
        />
      </button>

      {open && (
        <div
          role="group"
          aria-label={groupLabel}
          className="absolute right-0 top-[calc(100%+0.375rem)] z-20 max-h-72 w-56 overflow-y-auto rounded-xl border border-line bg-surface p-1.5 shadow-lg"
        >
          {active && (
            <button
              type="button"
              onClick={() => onChange(new Set())}
              className="mb-1 w-full rounded-lg px-2.5 py-1.5 text-left text-xs font-semibold text-brand hover:bg-brand-soft"
            >
              Clear
            </button>
          )}
          {options.map((option) => (
            <label
              key={option.id}
              className="flex min-h-9 cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-sm hover:bg-surface-2"
            >
              <input
                type="checkbox"
                checked={selected.has(option.id)}
                onChange={() => toggle(option.id)}
                className="size-4 shrink-0 rounded border-line accent-brand"
              />
              <span className="flex-1 truncate">{option.label}</span>
              {option.count !== undefined && (
                <span className="font-mono text-xs tabular-nums text-faint">
                  {option.count.toLocaleString()}
                </span>
              )}
            </label>
          ))}
        </div>
      )}
    </div>
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
