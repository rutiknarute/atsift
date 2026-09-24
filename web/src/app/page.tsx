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
import { AppSidebar } from "@/components/app-sidebar"
import { AnalyticsView, recordApplication } from "@/components/analytics-view"
import { ForMeView } from "@/components/for-me-view"
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
  boards_with_jobs: 0,
  board_errors: 0,
  title_matches: 0,
  non_us_jobs: 0,
  date_matches: 0,
  matches: 0,
  analyzed: 0,
  analyzed_total: 0,
  lookback_hours: null,
  dataset: null,
  started_at: null,
  finished_at: null,
  error: null,
}

type MetaResponse = ScannerMeta & {
  scanner_available: boolean
  role: "owner" | "demo" | null
}
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
  const [isDemo, setIsDemo] = useState(false)
  const [loadingMeta, setLoadingMeta] = useState(true)
  const [loadingJobs, setLoadingJobs] = useState(true)
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [retryNonce, setRetryNonce] = useState(0)

  const [lookbackHours, setLookbackHours] = useState(24)
  const [dataset, setDataset] = useState("core")
  const [analysisMode, setAnalysisMode] = useState<"fast" | "full">("fast")
  const [activeSection, setActiveSection] = useState<"scan" | "analytics" | "for-me">("scan")

  const [connectionLost, setConnectionLost] = useState(false)
  const jobsRequest = useRef(0)
  const pendingApplied = useRef(new Set<string>())
  const wasRunning = useRef(false)
  const defaultsSet = useRef(false)

  const running = status?.state === "running"
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
      const requestId = ++jobsRequest.current
      await Promise.resolve()
      if (!signal?.aborted && !quiet) setLoadingJobs(true)

      try {
        const data = await fetchJson<JobsWithSource>(
          `/api/jobs?lookback_hours=${lookbackHours}`,
          { signal },
        )

        if (signal?.aborted || requestId !== jobsRequest.current) return
        if (quiet && data.source === "snapshot" && wasRunning.current) {
          setConnectionLost(true)
          return
        }
        setJobs((data.jobs ?? []).map((job) => pendingApplied.current.has(job.uid) ? { ...job, viewed: true } : job))
        setSource(data.source ?? "snapshot")
        setScannedAt(data.scanned_at ?? null)
      } catch (loadError) {
        if (!isAbortError(loadError) && !signal?.aborted && !quiet) {
          setError(
            "Could not load results. Check the connection and try again.",
          )
        }
      } finally {
        if (!signal?.aborted) setLoadingJobs(false)
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
        setIsDemo(data.role === "demo")

        if (!defaultsSet.current) {
          setLookbackHours(data.default_lookback_hours)
          setDataset(data.datasets[0]?.id ?? "core")
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
    let timer: ReturnType<typeof setTimeout>
    async function refresh() {
      if (controller.signal.aborted) return
      if (!document.hidden) await loadJobs(controller.signal, true)
      if (!controller.signal.aborted) timer = setTimeout(refresh, STREAM_MS)
    }
    timer = setTimeout(refresh, STREAM_MS)

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [status?.state, loadJobs])

  // Poll status while a scan runs, and refresh results when it lands.
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let controller: AbortController | null = null

    async function poll() {
      if (document.hidden) {
        timer = setTimeout(poll, 15_000)
        return
      }
      controller = new AbortController()

      try {
        const data = await fetchJson<StatusResponse>("/api/status", {
          signal: controller.signal,
        })

        if (cancelled) return

        if (!data.scanner_available && wasRunning.current) {
          setConnectionLost(true)
          return
        }
        setConnectionLost(false)
        setStatus(data)
        setScannerAvailable(data.scanner_available)

        if (wasRunning.current && data.state !== "running") {
          void loadJobs(controller.signal)
        }

        if (data.state !== "running") setStopping(false)
        wasRunning.current = data.state === "running"
      } catch (pollError) {
        // A dropped poll is not worth surfacing; the next one will tell.
        if (isAbortError(pollError)) return
        setConnectionLost(true)
      } finally {
        controller = null
        if (!cancelled) timer = setTimeout(poll, wasRunning.current ? POLL_MS : 15_000)
      }
    }

    function onVisible() {
      if (!document.hidden && !controller) {
        if (timer) clearTimeout(timer)
        void poll()
      }
    }
    document.addEventListener("visibilitychange", onVisible)
    void poll()

    return () => {
      document.removeEventListener("visibilitychange", onVisible)
      cancelled = true
      controller?.abort()
      if (timer) clearTimeout(timer)
    }
  }, [loadJobs, running])

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
          analysis_mode: analysisMode,
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

  const markApplied = useCallback(async (uid: string) => {
    pendingApplied.current.add(uid)
    const appliedJob = jobs.find((job) => job.uid === uid)
    recordApplication(uid, appliedJob ? {
      title: appliedJob.title,
      company: appliedJob.company,
      categories: appliedJob.categories,
    } : undefined)
    setJobs((current) =>
      current.map((job) => (job.uid === uid ? { ...job, viewed: true } : job)),
    )

    if (isDemo) return

    try {
      await fetchJson("/api/jobs/viewed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid }),
      })
    } catch {
      setJobs((current) => current.map((job) => job.uid === uid ? { ...job, viewed: false } : job))
      setError("The job opened, but its applied status could not be saved. Check your connection and try again.")
      pendingApplied.current.delete(uid)
    }
  }, [isDemo, jobs])

  function retry() {
    setError(null)
    setLoadingMeta(true)
    setLoadingJobs(true)
    setRetryNonce((value) => value + 1)
  }

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <AppSidebar activeSection={activeSection} onSectionChange={setActiveSection} />
      <div className="min-w-0 flex-1">
      <a href="#main-content" className="skip-link">
        Skip to results
      </a>

      <header className="border-b border-line/70 bg-white/70 backdrop-blur-xl">
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

          {isDemo && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-line bg-brand-soft px-3 py-1.5 text-xs font-semibold text-brand-deep">
              Demo account
            </span>
          )}

          <button
            type="button"
            onClick={signOut}
            aria-label="Sign out"
            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-faint transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <LogOut aria-hidden="true" className="size-3.5" />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="min-h-[calc(100dvh-8rem)]">
        {activeSection === "analytics" ? <AnalyticsView /> : activeSection === "for-me" ? <ForMeView jobs={jobs} onApply={markApplied} loading={loadingJobs} source={source} /> : <>
        <section className="hero-stage border-b border-line">
          <div className="mx-auto w-full max-w-5xl px-5 py-10 text-center sm:py-14">
            <p className="label text-brand">{meta ? `${(meta.catalog_total ?? meta.datasets.reduce((total, entry) => total + entry.count, 0)).toLocaleString()} company boards` : "Scan company career boards"}</p>

            <h1 className="hero-heading mx-auto mt-3 max-w-4xl text-balance text-[2.5rem] leading-[1.02] sm:text-5xl lg:text-6xl">
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
                  analysisMode={status?.state === "running" ? status.analysis_mode ?? analysisMode : analysisMode}
                  onAnalysisModeChange={setAnalysisMode}
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
                  scannerAvailable={scannerAvailable && !isDemo}
                  activeLookbackHours={status?.lookback_hours ?? null}
                  activeDataset={status?.dataset ?? null}
                  demo={isDemo}
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

          {connectionLost && (
            <p role="status" className="rounded-xl border border-line bg-surface px-4 py-3 text-sm text-muted">
              Connection interrupted. Reconnecting automatically; the last results remain available.
            </p>
          )}

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
        </>}
      </main>

      <footer className="border-t border-line">
        <div
          className={cn(
            SHELL,
            "flex justify-center py-10 sm:py-12",
          )}
        >
          <BrandLogo className="h-14 w-auto sm:h-20" />
        </div>
      </footer>

      {/* Fixed to the viewport, so these live outside the page flow. */}
      <ScrollTop />
      {jobs.length > 0 && (
        <JobScout
          sampleMode={source === "snapshot"}
          onApply={markApplied}
          // Reads the same job list the results grid does, so a role applied
          // to in either place shows as applied in both.
          applied={(uid) =>
            Boolean(jobs.find((job) => job.uid === uid)?.viewed)
          }
        />
      )}
      </div>
    </div>
  )
}
