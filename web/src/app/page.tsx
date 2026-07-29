"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { RunConsole, RunConsoleSkeleton } from "@/components/run-console"
import { ScanProgress } from "@/components/scan-progress"
import { Results } from "@/components/results"
import { JobScout } from "@/components/job-scout"
import type {
  Job,
  JobsResponse,
  ScanStatus,
  ScannerMeta,
} from "@/lib/types"

const POLL_MS = 1_500

export default function Page() {
  const [meta, setMeta] = useState<(ScannerMeta & { scanner_available: boolean }) | null>(null)
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [source, setSource] = useState<"scanner" | "snapshot">("snapshot")
  const [scannedAt, setScannedAt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [lookbackHours, setLookbackHours] = useState(24)
  const [dataset, setDataset] = useState("main")

  const wasRunning = useRef(false)

  const loadJobs = useCallback(async () => {
    try {
      const response = await fetch(`/api/jobs?lookback_hours=${lookbackHours}`)
      const data = (await response.json()) as JobsResponse & {
        source: "scanner" | "snapshot"
      }

      setJobs(data.jobs ?? [])
      setSource(data.source ?? "snapshot")
      setScannedAt(data.scanned_at ?? null)
    } catch {
      setError("Could not load results.")
    }
  }, [lookbackHours])

  // Initial load.
  useEffect(() => {
    const controller = new AbortController()

    fetch("/api/meta", { signal: controller.signal })
      .then((response) => response.json())
      .then((data) => {
        if (!controller.signal.aborted) setMeta(data)
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("Could not reach the app.")
      })

    return () => controller.abort()
  }, [])

  // Reload results whenever the chosen window changes. Aborting on cleanup
  // keeps a slow response from overwriting a newer one.
  useEffect(() => {
    const controller = new AbortController()

    fetch(`/api/jobs?lookback_hours=${lookbackHours}`, {
      signal: controller.signal,
    })
      .then((response) => response.json())
      .then((data: JobsResponse & { source: "scanner" | "snapshot" }) => {
        if (controller.signal.aborted) return

        setJobs(data.jobs ?? [])
        setSource(data.source ?? "snapshot")
        setScannedAt(data.scanned_at ?? null)
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("Could not load results.")
      })

    return () => controller.abort()
  }, [lookbackHours])

  // Poll status while a scan runs, and refresh results when it lands.
  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const response = await fetch("/api/status")
        const data = (await response.json()) as ScanStatus & {
          scanner_available: boolean
        }

        if (cancelled) return

        setStatus(data)

        if (wasRunning.current && data.state !== "running") {
          void loadJobs()
        }

        wasRunning.current = data.state === "running"
      } catch {
        // A dropped poll is not worth surfacing; the next one will tell.
      }
    }

    void poll()
    const timer = setInterval(poll, POLL_MS)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [loadJobs])

  async function runScan() {
    setError(null)

    try {
      const response = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Categories are no longer a scan input — the sweep always applies the
        // full boolean search, and the results view filters by role instead.
        body: JSON.stringify({
          lookback_hours: lookbackHours,
          dataset,
        }),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        setError(data.error ?? "Could not start the scan.")
        return
      }

      wasRunning.current = true
      setStatus((current) =>
        current ? { ...current, state: "running", phase: "starting" } : current,
      )
    } catch {
      setError("Could not start the scan.")
    }
  }

  async function stopScan() {
    await fetch("/api/scan/stop", { method: "POST" }).catch(() => {})
  }

  async function markViewed(uid: string) {
    setJobs((current) =>
      current.map((job) => (job.uid === uid ? { ...job, viewed: true } : job)),
    )

    await fetch("/api/jobs/viewed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uid }),
    }).catch(() => {})
  }

  const running = status?.state === "running"
  const scannerAvailable = meta?.scanner_available ?? false

  return (
    <main className="relative min-h-screen">
      <div className="aurora" aria-hidden="true" />

      <div className="relative mx-auto w-full max-w-5xl px-5 py-14 sm:py-20">
        <header className="mb-10">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-accent" />
            <span className="font-mono text-xs uppercase tracking-[0.2em] text-faint">
              ATSift
            </span>
          </div>

          <h1 className="mt-5 text-balance text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
            Pick a timeframe.
            <br />
            <span className="text-accent">Hit run.</span> Get fresh roles.
          </h1>

          <p className="mt-4 max-w-xl text-pretty leading-relaxed text-muted">
            Sweeps 18,000 company job boards across six ATS platforms, keeps only
            non-senior roles matching your search, and screens each one for US
            location and OPT eligibility.
          </p>
        </header>

        <div className="flex flex-col gap-6">
          {meta ? (
            <RunConsole
              meta={meta}
              lookbackHours={lookbackHours}
              onLookbackChange={setLookbackHours}
              dataset={dataset}
              onDatasetChange={setDataset}
              running={running}
              scannerAvailable={scannerAvailable}
              onRun={runScan}
              onStop={stopScan}
            />
          ) : (
            <RunConsoleSkeleton />
          )}

          {status && <ScanProgress status={status} />}

          {error && (
            <p
              role="alert"
              className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger"
            >
              {error}
            </p>
          )}

          <Results
            jobs={jobs}
            source={source}
            lookbackHours={lookbackHours}
            scannedAt={scannedAt}
            onView={markViewed}
          />

          {jobs.length > 0 && <JobScout />}
        </div>

        <footer className="mt-16 border-t border-line-soft pt-6 text-xs text-faint">
          Greenhouse · Ashby · Lever · SmartRecruiters · Workable · Workday
        </footer>
      </div>
    </main>
  )
}
