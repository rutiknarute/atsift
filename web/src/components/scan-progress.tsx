"use client"

import { Check, Loader2, X } from "lucide-react"

import { cn, pct } from "@/lib/utils"
import type { ScanStatus } from "@/lib/types"

const PHASES = [
  { id: "fetching", label: "Sweeping boards" },
  { id: "screening", label: "Screening locations" },
  { id: "descriptions", label: "Reading descriptions" },
  { id: "analyzing", label: "AI screening" },
] as const

interface ScanProgressProps {
  status: ScanStatus
}

export function ScanProgress({ status }: ScanProgressProps) {
  const running = status.state === "running"

  if (!running && status.state !== "error") return null

  const activeIndex = PHASES.findIndex((p) => p.id === status.phase)

  const progress =
    status.phase === "analyzing"
      ? pct(status.analyzed, status.analyzed_total)
      : pct(status.companies_done, status.companies_total)

  return (
    <section
      aria-live="polite"
      className="rise rounded-[var(--radius-card)] border border-accent/30 bg-surface/70 p-6 backdrop-blur-xl"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          {status.state === "error" ? (
            <X className="size-4 text-danger" />
          ) : (
            <Loader2 className="size-4 animate-spin text-accent" />
          )}
          <span className="text-sm font-medium">
            {status.message || "Working…"}
          </span>
        </div>

        <span className="font-mono text-sm tabular-nums text-accent">
          {progress}%
        </span>
      </div>

      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      <ol className="mt-5 grid gap-2 sm:grid-cols-4">
        {PHASES.map((phase, index) => {
          const done = activeIndex > index
          const active = activeIndex === index

          return (
            <li
              key={phase.id}
              className={cn(
                "flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition-colors",
                active && "border-accent/40 bg-accent/10 text-text",
                done && "border-line-soft bg-surface-2/50 text-muted",
                !active && !done && "border-line-soft/50 text-faint",
              )}
            >
              {done ? (
                <Check className="size-3 shrink-0 text-accent" />
              ) : active ? (
                <Loader2 className="size-3 shrink-0 animate-spin text-accent" />
              ) : (
                <span className="size-3 shrink-0 rounded-full border border-current opacity-40" />
              )}
              <span className="truncate">{phase.label}</span>
            </li>
          )
        })}
      </ol>

      <dl className="mt-5 grid grid-cols-3 gap-3 border-t border-line-soft pt-4">
        <Stat
          label="Boards swept"
          value={`${status.companies_done.toLocaleString()} / ${status.companies_total.toLocaleString()}`}
        />
        <Stat label="Matches" value={status.jobs_found.toLocaleString()} />
        <Stat
          label="AI screened"
          value={
            status.analyzed_total
              ? `${status.analyzed} / ${status.analyzed_total}`
              : "—"
          }
        />
      </dl>

      {status.error && (
        <p className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {status.error}
        </p>
      )}
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-faint">
        {label}
      </dt>
      <dd className="mt-0.5 font-mono text-sm tabular-nums">{value}</dd>
    </div>
  )
}
