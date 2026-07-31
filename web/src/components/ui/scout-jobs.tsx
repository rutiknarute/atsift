"use client"

import { ArrowUpRight, CheckCircle2, CircleAlert, MapPin } from "lucide-react"

import { cn, formatAge } from "@/lib/utils"
import type { ScoutJob, ScoutSearchResult } from "@/lib/types"

/*
  The Scout's results, rendered from the search tool's own output rather than
  from the model's prose.

  The model is told not to list the jobs back, precisely so these cards are the
  single place a role appears. It also means a title, company or link can never
  drift from what the tool actually found — the model does not get to retype
  them.
*/

function isScoutJob(value: unknown): value is ScoutJob {
  if (typeof value !== "object" || value === null) return false

  const job = value as Partial<ScoutJob>

  return typeof job.uid === "string" && typeof job.title === "string"
}

/** Narrow an unknown tool output, since a stream can carry anything. */
export function readSearchResult(output: unknown): ScoutSearchResult | null {
  if (typeof output !== "object" || output === null) return null

  const result = output as Partial<ScoutSearchResult>

  if (!Array.isArray(result.jobs)) return null

  return {
    source: result.source === "scanner" ? "scanner" : "snapshot",
    searchedWithinHours: result.searchedWithinHours ?? null,
    totalInWindow: result.totalInWindow ?? 0,
    matchCount: result.matchCount ?? result.jobs.length,
    jobs: result.jobs.filter(isScoutJob),
  }
}

function experienceLabel(years: number | null): string | null {
  if (typeof years !== "number") return null
  if (years === 0) return "No experience listed"

  return `${years}+ yrs`
}

export function ScoutJobs({
  result,
  onApply,
  applied,
}: {
  result: ScoutSearchResult
  onApply?: (uid: string) => void
  applied?: (uid: string) => boolean
}) {
  if (result.jobs.length === 0) return null

  return (
    <ul className="mt-3 flex flex-col gap-2">
      {result.jobs.map((job) => {
        const years = experienceLabel(job.minimumYears)
        const isApplied = applied?.(job.uid) ?? false

        return (
          <li
            key={job.uid}
            className="rounded-xl border border-line bg-surface p-3 transition-colors hover:border-brand-line"
          >
            <p className="text-pretty text-[0.9rem] font-semibold leading-snug text-text">
              {job.title}
            </p>
            <p className="mt-0.5 text-[0.8rem] font-medium text-brand">
              {job.company}
            </p>

            {job.location && (
              <p className="mt-1 flex items-start gap-1 text-[0.75rem] leading-snug text-faint">
                <MapPin aria-hidden="true" className="mt-px size-3 shrink-0" />
                <span className="break-words">{job.location}</span>
              </p>
            )}

            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              {job.ageHours !== null && <Chip>{formatAge(job.ageHours)}</Chip>}
              {years && <Chip>{years}</Chip>}

              {job.optEligible === "NO" ? (
                <Chip tone="danger">
                  <CircleAlert aria-hidden="true" className="size-3" />
                  Blocks OPT
                </Chip>
              ) : job.optEligible === "YES" ? (
                <Chip tone="brand">
                  <CheckCircle2 aria-hidden="true" className="size-3" />
                  OPT
                </Chip>
              ) : null}
            </div>

            {job.applyUrl && (
              <a
                href={job.applyUrl}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => onApply?.(job.uid)}
                className={cn(
                  "mt-3 inline-flex min-h-9 w-full items-center justify-center gap-1.5 rounded-lg px-3",
                  "text-[0.8rem] font-semibold transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
                  isApplied
                    ? "border border-brand-line bg-brand-soft text-brand-deep hover:bg-brand-soft/70"
                    : "bg-brand text-brand-ink hover:bg-brand-strong",
                )}
              >
                {isApplied ? (
                  <>
                    <CheckCircle2 aria-hidden="true" className="size-3.5" />
                    Already Applied
                  </>
                ) : (
                  <>
                    Apply now
                    <ArrowUpRight aria-hidden="true" className="size-3" />
                  </>
                )}
              </a>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function Chip({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode
  tone?: "neutral" | "brand" | "danger"
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[0.7rem] font-medium",
        tone === "neutral" && "bg-surface-2 text-muted",
        tone === "brand" && "border border-brand-line bg-brand-soft text-brand-deep",
        tone === "danger" && "border border-danger-line bg-danger-bg text-danger",
      )}
    >
      {children}
    </span>
  )
}
