"use client"

import { Play, Square, Loader2 } from "lucide-react"

import { cn, formatWindow } from "@/lib/utils"
import type { CategoryId, ScannerMeta } from "@/lib/types"

interface RunConsoleProps {
  meta: ScannerMeta
  lookbackHours: number
  onLookbackChange: (hours: number) => void
  dataset: string
  onDatasetChange: (dataset: string) => void
  categories: CategoryId[]
  onCategoriesChange: (categories: CategoryId[]) => void
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
  categories,
  onCategoriesChange,
  running,
  scannerAvailable,
  onRun,
  onStop,
}: RunConsoleProps) {
  function toggleCategory(id: CategoryId) {
    onCategoriesChange(
      categories.includes(id)
        ? categories.filter((c) => c !== id)
        : [...categories, id],
    )
  }

  const activeDataset = meta.datasets.find((d) => d.id === dataset)

  return (
    <section className="relative">
      <div className="rounded-[var(--radius-card)] border border-line bg-surface/70 p-6 backdrop-blur-xl sm:p-8">
        {/* Step 1 — the timeframe. The one input that matters. */}
        <div className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between gap-4">
            <label className="text-sm font-medium text-muted">
              <span className="mr-2 font-mono text-xs text-accent">01</span>
              Pick your timeframe
            </label>
            <span className="text-xs text-faint">
              max {formatWindow(meta.max_lookback_hours)}
            </span>
          </div>

          <div
            role="radiogroup"
            aria-label="Lookback window"
            className="grid grid-cols-5 gap-2"
          >
            {meta.lookback_options.map((hours) => {
              const active = hours === lookbackHours

              return (
                <button
                  key={hours}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  disabled={running}
                  onClick={() => onLookbackChange(hours)}
                  className={cn(
                    "group relative rounded-xl border px-2 py-4 transition-all duration-200",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                    active
                      ? "border-accent bg-accent/10 shadow-[0_0_0_1px_var(--color-accent)]"
                      : "border-line-soft bg-surface-2/50 hover:border-faint hover:bg-surface-2",
                  )}
                >
                  <span
                    className={cn(
                      "block text-2xl font-semibold tabular-nums transition-colors",
                      active ? "text-accent" : "text-text",
                    )}
                  >
                    {hours}
                  </span>
                  <span className="mt-0.5 block text-[11px] uppercase tracking-wide text-faint">
                    hours
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Step 2 — scope. Sensible defaults, so this is optional. */}
        <div className="mt-7 flex flex-col gap-3">
          <label className="text-sm font-medium text-muted">
            <span className="mr-2 font-mono text-xs text-accent">02</span>
            Narrow the roles
            <span className="ml-2 text-xs text-faint">
              (all of them, if you pick none)
            </span>
          </label>

          <div className="flex flex-wrap gap-2">
            {meta.categories.map((category) => {
              const active = categories.includes(category.id)

              return (
                <button
                  key={category.id}
                  type="button"
                  aria-pressed={active}
                  disabled={running}
                  onClick={() => toggleCategory(category.id)}
                  className={cn(
                    "rounded-full border px-3.5 py-1.5 text-sm transition-all duration-200",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                    active
                      ? "border-accent bg-accent text-accent-ink font-medium"
                      : "border-line-soft bg-surface-2/50 text-muted hover:border-faint hover:text-text",
                  )}
                >
                  {category.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* Step 3 — the catalog to sweep. */}
        <div className="mt-7 flex flex-col gap-3">
          <label className="text-sm font-medium text-muted">
            <span className="mr-2 font-mono text-xs text-accent">03</span>
            Choose the catalog
          </label>

          <div className="grid gap-2 sm:grid-cols-2">
            {meta.datasets.map((option) => {
              const active = option.id === dataset

              return (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={active}
                  disabled={running}
                  onClick={() => onDatasetChange(option.id)}
                  className={cn(
                    "rounded-xl border px-4 py-3 text-left transition-all duration-200",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                    active
                      ? "border-accent bg-accent/10"
                      : "border-line-soft bg-surface-2/50 hover:border-faint",
                  )}
                >
                  <span className="block text-sm font-medium tabular-nums">
                    {option.count.toLocaleString()} companies
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-faint">
                    {option.label}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* The action. */}
        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
          {running ? (
            <button
              type="button"
              onClick={onStop}
              className={cn(
                "group inline-flex flex-1 items-center justify-center gap-2.5 rounded-xl",
                "border border-danger/40 bg-danger/10 px-6 py-4 text-base font-semibold text-danger",
                "transition-all duration-200 hover:bg-danger/20",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger",
              )}
            >
              <Square className="size-4 fill-current" />
              Stop scan
            </button>
          ) : (
            <button
              type="button"
              onClick={onRun}
              disabled={!scannerAvailable}
              className={cn(
                "group inline-flex flex-1 items-center justify-center gap-2.5 rounded-xl",
                "bg-accent px-6 py-4 text-base font-semibold text-accent-ink",
                "transition-all duration-200",
                "hover:brightness-110 active:scale-[0.99]",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
                "disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-faint",
              )}
            >
              <Play className="size-4 fill-current transition-transform group-hover:translate-x-0.5" />
              Run scan
              <span className="font-normal opacity-70">
                · last {formatWindow(lookbackHours)}
              </span>
            </button>
          )}
        </div>

        {!scannerAvailable && (
          <p className="mt-3 text-center text-xs text-warn">
            The scanner isn&apos;t reachable, so live scanning is off. You&apos;re
            browsing a packaged snapshot.
          </p>
        )}

        {scannerAvailable && activeDataset && !running && (
          <p className="mt-3 text-center text-xs text-faint">
            Sweeps {activeDataset.count.toLocaleString()} job boards for postings
            from the last {formatWindow(lookbackHours)}.
          </p>
        )}
      </div>
    </section>
  )
}

export function RunConsoleSkeleton() {
  return (
    <div className="shimmer h-[30rem] rounded-[var(--radius-card)] border border-line bg-surface/70">
      <span className="sr-only">Loading controls</span>
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-5 animate-spin text-faint" />
      </div>
    </div>
  )
}
