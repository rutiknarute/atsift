"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { Archive, CircleAlert, LogOut, RadioTower, RefreshCw } from "lucide-react"

import { RunConsole, RunConsoleSkeleton } from "@/components/run-console"
import { ScanProgress } from "@/components/scan-progress"
import { Results } from "@/components/results"
import { JobScout } from "@/components/job-scout"
import { ScrollTop } from "@/components/scroll-top"
import { BrandLogo } from "@/components/brand"
import { VanishingWord } from "@/components/vanishing-word"
import { cn } from "@/lib/utils"
import type {
  Job,
  JobsResponse,
  ScanStatus,
  ScannerMeta,
} from "@/lib/types"

const POLL_MS = 1_500
const STREAM_MS = 4_000

/*
  Shell width. The job cards sit two-up inside this, so widening it is what
  makes each card wider — and because the content reflows, wider cards are
  also shorter. Header and footer share it so nothing drifts out of line.
*/
const SHELL = "mx-auto w-full max-w-[84rem] px-5"

const EMPTY_STATUS: ScanStatus = {
  state: "idle",
  phase: "",
  message: "",
  companies_done: 0,
  companies_total: 0,
  jobs_found: 0,
  matches: 0,
  analyzed: 0,
  analyzed_total: 0,
  lookback_hours: null,
  dataset: null,
  started_at: null,
  finished_at: null,
  error: null,
}

type MetaResponse = ScannerMeta & { scanner_available: boolean }
type JobsWithSource = JobsResponse & { source: "scanner" | "snapshot" }
type StatusResponse = ScanStatus & { scanner_available: boolean }

async function fetchJson<T>(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init)
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message =
      data &&
      typeof data === "object" &&
      "error" in data &&
      typeof data.error === "string"
        ? data.error
        : `Request failed with status ${response.status}.`

    throw new Error(message)
  }

  if (data === null) throw new Error("The server returned an invalid response.")

  return data as T
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError"
}

export default function Page() {
  const [meta, setMeta] = useState<ScannerMeta | null>(null)
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [source, setSource] = useState<"scanner" | "snapshot">("snapshot")
  const [scannedAt, setScannedAt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [scannerAvailable, setScannerAvailable] = useState(false)
  const [loadingMeta, setLoadingMeta] = useState(true)
  const [loadingJobs, setLoadingJobs] = useState(true)
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [retryNonce, setRetryNonce] = useState(0)

  const [lookbackHours, setLookbackHours] = useState(24)
  const [dataset, setDataset] = useState("main")

  const wasRunning = useRef(false)
  const defaultsSet = useRef(false)

  const router = useRouter()

  const signOut = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" })

    // `replace`, not `push`: Back should not return to a page the session no
    // longer opens.
    router.replace("/login")
    router.refresh()
  }, [router])

  // `quiet` is for the refreshes that happen on their own during a scan: they
  // must not raise the loading state or surface an error, or a list the user
  // is already reading would flicker and nag on every tick.
  const loadJobs = useCallback(
    async (signal?: AbortSignal, quiet = false) => {
      await Promise.resolve()
      if (!signal?.aborted && !quiet) setLoadingJobs(true)

      try {
        const data = await fetchJson<JobsWithSource>(
          `/api/jobs?lookback_hours=${lookbackHours}`,
          { signal },
        )

        if (signal?.aborted) return
        setJobs(data.jobs ?? [])
        setSource(data.source ?? "snapshot")
        setScannedAt(data.scanned_at ?? null)
      } catch (loadError) {
        if (!isAbortError(loadError) && !signal?.aborted && !quiet) {
          setError(
            "Could not load results. Check the connection and try again.",
          )
        }
      } finally {
        if (!signal?.aborted && !quiet) setLoadingJobs(false)
      }
    },
    [lookbackHours],
  )

  // Load scan metadata. The route itself has an offline fallback, so an error
  // here means the Next.js app could not answer at all.
  useEffect(() => {
    const controller = new AbortController()

    void fetchJson<MetaResponse>("/api/meta", { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return

        setMeta(data)
        setScannerAvailable(data.scanner_available)

        if (!defaultsSet.current) {
          setLookbackHours(data.default_lookback_hours)
          setDataset(data.datasets[0]?.id ?? "main")
          defaultsSet.current = true
        }
      })
      .catch((metaError) => {
        if (!isAbortError(metaError) && !controller.signal.aborted) {
          setError(
            "Could not load the scan controls. Check the connection and try again.",
          )
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingMeta(false)
      })

    return () => controller.abort()
  }, [retryNonce])

  // Reload results whenever the chosen window changes. Aborting on cleanup
  // keeps a slow response from overwriting a newer one.
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => {
      void loadJobs(controller.signal)
    }, 0)

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [loadJobs, retryNonce])

  /*
    Results stream in while the scan is still working. The scanner republishes
    its store every few seconds as each posting clears AI screening, so polling
    it here makes the list grow underneath the progress panel rather than
    staying empty until the whole sweep finishes.
  */
  useEffect(() => {
    if (status?.state !== "running") return

    const controller = new AbortController()
    const timer = setInterval(() => {
      void loadJobs(controller.signal, true)
    }, STREAM_MS)

    return () => {
      clearInterval(timer)
      controller.abort()
    }
  }, [status?.state, loadJobs])

  // Poll status while a scan runs, and refresh results when it lands.
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let controller: AbortController | null = null

    async function poll() {
      controller = new AbortController()

      try {
        const data = await fetchJson<StatusResponse>("/api/status", {
          signal: controller.signal,
        })

        if (cancelled) return

        setStatus(data)
        setScannerAvailable(data.scanner_available)

        if (wasRunning.current && data.state !== "running") {
          void loadJobs()
        }

        if (data.state !== "running") setStopping(false)
        wasRunning.current = data.state === "running"
      } catch (pollError) {
        // A dropped poll is not worth surfacing; the next one will tell.
        if (isAbortError(pollError)) return
      } finally {
        if (!cancelled) timer = setTimeout(poll, POLL_MS)
      }
    }

    void poll()

    return () => {
      cancelled = true
      controller?.abort()
      if (timer) clearTimeout(timer)
    }
  }, [loadJobs])

  async function runScan() {
    setError(null)
    setStarting(true)

    try {
      const data = await fetchJson<{ status?: ScanStatus }>("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Categories are no longer a scan input — the sweep always applies the
        // full boolean search, and the results view filters by role instead.
        body: JSON.stringify({
          lookback_hours: lookbackHours,
          dataset,
        }),
      })

      wasRunning.current = true
      setStatus(
        data.status ?? {
          ...EMPTY_STATUS,
          state: "running",
          phase: "starting",
          message: "Starting scan…",
          lookback_hours: lookbackHours,
          dataset,
        },
      )
    } catch (scanError) {
      setError(
        scanError instanceof Error
          ? `${scanError.message} Check the scanner and try again.`
          : "Could not start the scan. Check the scanner and try again.",
      )
    } finally {
      setStarting(false)
    }
  }

  async function stopScan() {
    setError(null)
    setStopping(true)

    try {
      await fetchJson("/api/scan/stop", { method: "POST" })
    } catch {
      setStopping(false)
      setError("Could not stop the scan. Wait a moment and try again.")
    }
  }

  async function markApplied(uid: string) {
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

  function retry() {
    setError(null)
    setLoadingMeta(true)
    setLoadingJobs(true)
    setRetryNonce((value) => value + 1)
  }

  return (
    <>
      <a href="#main-content" className="skip-link">
        Skip to results
      </a>

      <header className="border-b border-line bg-bg">
        <div className={cn(SHELL, "flex min-h-16 items-center gap-3")}>
          <BrandLogo />

          <span
            role="status"
            className="ml-auto inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium text-muted"
          >
            {scannerAvailable ? (
              <RadioTower aria-hidden="true" className="size-3.5 text-brand" />
            ) : (
              <Archive aria-hidden="true" className="size-3.5" />
            )}
            {loadingMeta
              ? "Checking scanner…"
              : scannerAvailable
                ? "Scanner online"
                : "Snapshot mode"}
          </span>

          <button
            type="button"
            onClick={signOut}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-faint transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <LogOut aria-hidden="true" className="size-3.5" />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="min-h-[calc(100dvh-8rem)]">
        <section className="grid-paper border-b border-line">
          <div className="mx-auto w-full max-w-5xl px-5 py-10 text-center sm:py-14">
            <p className="label text-brand">18,000+ verified company boards</p>

            <h1 className="mx-auto mt-3 max-w-4xl text-balance font-display text-[2.5rem] font-extrabold leading-[1.02] tracking-[-0.035em] sm:text-5xl lg:text-6xl">
              If you&rsquo;re not in the first 10 applicants, you&rsquo;re{" "}
              <VanishingWord word="invisible" />.
            </h1>

            <p className="mx-auto mt-4 max-w-2xl text-pretty text-base leading-relaxed text-muted sm:text-lg">
              Pick a window and sweep public ATS boards for fresh roles with
              confirmed US locations. The freshest matches get OPT screening
              and a JD breakdown.
            </p>

            <div className="mt-7">
              {meta ? (
                <RunConsole
                  meta={meta}
                  lookbackHours={lookbackHours}
                  onLookbackChange={(hours) => {
                    setError(null)
                    setLoadingJobs(true)
                    setLookbackHours(hours)
                  }}
                  dataset={dataset}
                  onDatasetChange={setDataset}
                  running={running}
                  starting={starting}
                  stopping={stopping}
                  scannerAvailable={scannerAvailable}
                  onRun={runScan}
                  onStop={stopScan}
                />
              ) : loadingMeta ? (
                <RunConsoleSkeleton />
              ) : (
                <div className="mx-auto flex max-w-xl items-center justify-center gap-3 rounded-xl border border-danger-line bg-danger-bg px-4 py-3 text-sm text-danger">
                  <CircleAlert aria-hidden="true" className="size-4 shrink-0" />
                  <span>Scan controls are unavailable.</span>
                  <button
                    type="button"
                    onClick={retry}
                    className="ml-auto inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 font-semibold underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger"
                  >
                    <RefreshCw aria-hidden="true" className="size-3.5" />
                    Retry
                  </button>
                </div>
              )}
            </div>
          </div>
        </section>

        <div className={cn(SHELL, "flex flex-col gap-5 py-7 sm:py-9")}>
          {status && <ScanProgress status={status} />}

          {error && (
            <div
              role="alert"
              className="flex items-start gap-3 rounded-xl border border-danger-line bg-danger-bg px-4 py-3 text-sm leading-relaxed text-danger"
            >
              <CircleAlert
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0"
              />
              <p className="flex-1">{error}</p>
              <button
                type="button"
                onClick={retry}
                className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-lg px-2 font-semibold underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger"
              >
                <RefreshCw aria-hidden="true" className="size-3.5" />
                Retry
              </button>
            </div>
          )}

          <Results
            jobs={jobs}
            source={source}
            lookbackHours={lookbackHours}
            scannedAt={scannedAt}
            loading={loadingJobs}
            onApply={markApplied}
          />
        </div>
      </main>

      <footer className="border-t border-line">
        <div
          className={cn(
            SHELL,
            "flex flex-col gap-2 py-6 text-xs text-faint sm:flex-row sm:items-center sm:justify-between",
          )}
        >
          <span translate="no">ATSift</span>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 sm:justify-end">
            <span>
              Greenhouse · Ashby · Lever · SmartRecruiters · Workable · Workday
            </span>
            <a
              href="https://logo.dev"
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-sm underline underline-offset-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              Company logos provided by Logo.dev
            </a>
          </div>
        </div>
      </footer>

      {/* Fixed to the viewport, so these live outside the page flow. */}
      <ScrollTop />
      {jobs.length > 0 && <JobScout sampleMode={source === "snapshot"} />}
    </>
  )
}
