"use client"

import {
  Archive,
  ChevronDown,
  Clock,
  Database,
  Loader2,
  RefreshCw,
  Square,
} from "lucide-react"

import { cn, formatWindow } from "@/lib/utils"
import type { ScannerMeta } from "@/lib/types"

interface RunConsoleProps {
  meta: ScannerMeta
  lookbackHours: number
  onLookbackChange: (hours: number) => void
  dataset: string
  onDatasetChange: (dataset: string) => void
  running: boolean
  starting: boolean
  stopping: boolean
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
  starting,
  stopping,
  scannerAvailable,
  onRun,
  onStop,
}: RunConsoleProps) {
  const controlsDisabled = running || starting

  return (
    <fieldset className="flex flex-col items-center gap-3">
      <legend className="sr-only">Configure and run a job-board scan</legend>

      <div className="grid w-full max-w-4xl gap-3 text-left sm:grid-cols-[13rem_minmax(16rem,1fr)_auto] sm:items-center">
        <Picker
          label="Time window"
          name="lookback"
          icon={<Clock aria-hidden="true" className="size-4 text-faint" />}
          value={String(lookbackHours)}
          onChange={(value) => onLookbackChange(Number(value))}
          disabled={controlsDisabled}
          options={meta.lookback_options.map((hours) => ({
            value: String(hours),
            label: `Scan last ${formatWindow(hours)}`,
          }))}
        />

        <Picker
          label="Board catalog"
          name="dataset"
          icon={<Database aria-hidden="true" className="size-4 text-faint" />}
          value={dataset}
          onChange={onDatasetChange}
          disabled={controlsDisabled}
          options={meta.datasets.map((option) => ({
            value: option.id,
            label: option.label,
          }))}
        />

        {running ? (
          <button
            type="button"
            onClick={onStop}
            disabled={stopping}
            className={cn(
              "inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border px-6 text-sm font-semibold",
              "border-danger-line bg-danger-bg text-danger transition-colors hover:border-danger hover:bg-danger-bg",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger focus-visible:ring-offset-2",
              "disabled:cursor-wait disabled:opacity-60",
            )}
          >
            {stopping ? (
              <Loader2 aria-hidden="true" className="size-4 animate-spin" />
            ) : (
              <Square
                aria-hidden="true"
                className="size-3.5 fill-current"
              />
            )}
            {stopping ? "Stopping…" : "Stop scan"}
          </button>
        ) : scannerAvailable ? (
          <button
            type="button"
            onClick={onRun}
            disabled={starting}
            className={cn(
              "inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-6 text-sm font-semibold",
              "bg-brand text-brand-ink transition-colors hover:bg-brand-strong",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
              "disabled:cursor-wait disabled:opacity-60",
            )}
          >
            {starting ? (
              <Loader2 aria-hidden="true" className="size-4 animate-spin" />
            ) : (
              <RefreshCw aria-hidden="true" className="size-4" />
            )}
            {starting ? "Starting…" : "Run fresh scan"}
          </button>
        ) : (
          <span className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-line bg-surface-2 px-5 text-sm font-medium text-muted">
            <Archive aria-hidden="true" className="size-4" />
            Snapshot only
          </span>
        )}
      </div>

      <p
        aria-live="polite"
        className="flex max-w-2xl items-start justify-center gap-2 text-center text-sm leading-relaxed text-muted"
      >
        <span
          className={cn(
            "mt-[0.45rem] size-1.5 shrink-0 rounded-full",
            running || scannerAvailable ? "bg-brand" : "bg-faint",
          )}
        />
        {running
          ? "Scanning now — roles appear below as each one is screened. You can stop at any time and keep what has landed."
          : scannerAvailable
            ? `Ready to sweep ${(meta.datasets.find((d) => d.id === dataset)?.count ?? 0).toLocaleString()} job boards.`
            : "The live scanner is offline. You can still browse the packaged sample below."}
      </p>
    </fieldset>
  )
}

function Picker({
  label,
  name,
  icon,
  value,
  onChange,
  options,
  disabled,
}: {
  label: string
  name: string
  icon: React.ReactNode
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  disabled?: boolean
}) {
  return (
    <label className="block min-w-0">
      {/*
        The selected option already says what the control does ("Scan last 24
        hours"), so the caption above it was repeating itself. It stays for
        screen readers, which only get the control, not the layout.
      */}
      <span className="sr-only">{label}</span>
      <span className="relative block">
        <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2">
          {icon}
        </span>

        <select
          name={name}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          className={cn(
            "min-h-12 w-full appearance-none truncate rounded-xl border border-line bg-surface",
            "pl-11 pr-10 text-sm text-text transition-colors",
            "hover:border-faint",
            "focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/25",
            "disabled:cursor-not-allowed disabled:opacity-60",
          )}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <ChevronDown
          aria-hidden="true"
          className="pointer-events-none absolute right-4 top-1/2 size-4 -translate-y-1/2 text-faint"
        />
      </span>
    </label>
  )
}

export function RunConsoleSkeleton() {
  return (
    <div className="shimmer mx-auto flex h-[4.5rem] w-full max-w-4xl items-center justify-center rounded-xl border border-line bg-surface">
      <Loader2 aria-hidden="true" className="size-4 animate-spin text-faint" />
      <span className="sr-only">Loading controls</span>
    </div>
  )
}
