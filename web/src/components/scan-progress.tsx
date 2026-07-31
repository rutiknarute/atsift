"use client"

import { Loader2, X } from "lucide-react"

import { cn, pct } from "@/lib/utils"
import type { ScanStatus } from "@/lib/types"

export function ScanProgress({ status }: { status: ScanStatus }) {
  const running = status.state === "running"

  if (!running && status.state !== "error") return null

  const progress = scanProgress(status)

  return (
    <section
      className="rise rounded-[var(--radius-card)] border border-line bg-surface p-5"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          {status.state === "error" ? (
            <X aria-hidden="true" className="size-4 text-danger" />
          ) : (
            <Loader2
              aria-hidden="true"
              className="size-4 animate-spin text-brand"
            />
          )}
          <span aria-live="polite" className="text-sm font-semibold">
            {status.message || "Working…"}
          </span>
        </div>

        <span className="font-mono text-sm tabular-nums text-muted">
          {progress}%
        </span>
      </div>

      <div
        role="progressbar"
        aria-label="Scan progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
        className="mt-4 h-1.5 overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className="h-full rounded-full bg-brand transition-[width] duration-300 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/*
        Counters, not phases. Every posting now runs the whole pipeline on its
        own, so there is no stage the scan is "in" — there is only how much has
        been read and how much has been listed, both climbing at once.
      */}
      <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-line-soft pt-4 sm:grid-cols-4">
        <Stat
          label="Boards read"
          value={`${status.companies_done.toLocaleString()} / ${status.companies_total.toLocaleString()}`}
        />
        <Stat label="Roles found" value={status.jobs_found.toLocaleString()} />
        <Stat
          label="AI screened"
          value={
            status.analyzed_total
              ? `${status.analyzed.toLocaleString()} / ${status.analyzed_total.toLocaleString()}`
              : "—"
          }
        />
        <Stat
          label="Listed below"
          value={status.matches.toLocaleString()}
          accent
        />
      </dl>

      {status.error && (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-danger-line bg-danger-bg px-3 py-2 text-xs text-danger"
        >
          {status.error}
        </p>
      )}
    </section>
  )
}

/*
  Two things run at once, so the bar weighs both: how much of the catalog has
  been read, and how much of what it produced has been screened. Screening
  trails the sweep, so it is never reported as finished while a posting is
  still waiting for the model.
*/
function scanProgress(status: ScanStatus): number {
  if (status.phase === "starting") return 2

  const swept = pct(status.companies_done, status.companies_total)
  const screened = status.analyzed_total
    ? pct(status.analyzed, status.analyzed_total)
    : swept

  return Math.min(99, Math.round(swept * 0.7 + screened * 0.3))
}

function Stat({
  label,
  value,
  accent = false,
}: {
  label: string
  value: string
  accent?: boolean
}) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd
        className={cn(
          "mt-1 font-mono text-sm tabular-nums",
          accent && "font-semibold text-brand",
        )}
      >
        {value}
      </dd>
    </div>
  )
}
