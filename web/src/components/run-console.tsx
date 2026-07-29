"use client"

import { Loader2, Play, Square } from "lucide-react"

import { SelectField } from "@/components/ui/select-field"
import { cn, formatWindow } from "@/lib/utils"
import type { ScannerMeta } from "@/lib/types"

interface RunConsoleProps {
  meta: ScannerMeta
  lookbackHours: number
  onLookbackChange: (hours: number) => void
  dataset: string
  onDatasetChange: (dataset: string) => void
  running: boolean
  scannerAvailable: boolean
  onRun: () => void
  onStop: () => void
}

export function RunConsole({
  meta,
  lookbackHours,
  onLookbackChange,
  dataset,
  onDatasetChange,
  running,
  scannerAvailable,
  onRun,
  onStop,
}: RunConsoleProps) {
  const activeDataset = meta.datasets.find((d) => d.id === dataset)

  return (
    <section className="rounded-[var(--radius-card)] border border-line bg-surface/70 p-5 backdrop-blur-xl sm:p-6">
      <div className="grid gap-4 sm:grid-cols-[1fr_1.4fr_auto] sm:items-end">
        <SelectField
          label="Timeframe"
          value={String(lookbackHours)}
          onChange={(value) => onLookbackChange(Number(value))}
          disabled={running}
          options={meta.lookback_options.map((hours) => ({
            value: String(hours),
            label: `Last ${formatWindow(hours)}`,
          }))}
        />

        <SelectField
          label="Catalog"
          value={dataset}
          onChange={onDatasetChange}
          disabled={running}
          options={meta.datasets.map((option) => ({
            value: option.id,
            label: `${option.count.toLocaleString()} companies — ${option.label}`,
          }))}
        />

        {running ? (
          <button
            type="button"
            onClick={onStop}
            className={cn(
              "inline-flex items-center justify-center gap-2 rounded-xl",
              "border border-danger/40 bg-danger/10 px-6 py-3 text-sm font-semibold text-danger",
              "transition-colors hover:bg-danger/20",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger",
            )}
          >
            <Square className="size-3.5 fill-current" />
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={onRun}
            disabled={!scannerAvailable}
            className={cn(
              "group inline-flex items-center justify-center gap-2 rounded-xl",
              "bg-accent px-7 py-3 text-sm font-semibold text-accent-ink",
              "transition-all hover:brightness-110 active:scale-[0.99]",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
              "disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-faint",
            )}
          >
            <Play className="size-3.5 fill-current transition-transform group-hover:translate-x-0.5" />
            Run scan
          </button>
        )}
      </div>

      <p className="mt-3 text-xs text-faint">
        {!scannerAvailable ? (
          <span className="text-warn">
            The scanner isn&apos;t reachable, so live scanning is off — showing a
            packaged snapshot.
          </span>
        ) : running ? (
          "Scanning. You can stop at any time; results found so far are kept."
        ) : activeDataset ? (
          `Sweeps ${activeDataset.count.toLocaleString()} job boards for postings from the last ${formatWindow(lookbackHours)}.`
        ) : null}
      </p>
    </section>
  )
}

export function RunConsoleSkeleton() {
  return (
    <div className="shimmer flex h-32 items-center justify-center rounded-[var(--radius-card)] border border-line bg-surface/70">
      <Loader2 className="size-5 animate-spin text-faint" />
      <span className="sr-only">Loading controls</span>
    </div>
  )
}
