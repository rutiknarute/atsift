import { NextResponse } from "next/server"

import { fetchScanner, scannerAvailable } from "@/server/scanner-client"
import { snapshotJobs } from "@/server/public-data"
import { normalizeJobExperience } from "@/lib/experience"
import type { Job, JobsResponse } from "@/lib/types"
import { withLogos } from "@/server/job-logo"
import { requireSession } from "@/server/guard"

function hasConfirmedUsLocation(job: Job) {
  if (!job.location_verdict) return true
  if (job.location_verdict === "US") return true
  if (job.location_verdict === "NON_US") return false

  return job.analysis?.us_location_eligible === "YES"
}

export async function GET(request: Request) {
  const denied = await requireSession()

  if (denied) return denied

  const { searchParams } = new URL(request.url)
  const query = searchParams.toString()

  if (await scannerAvailable()) {
    try {
      const data = await fetchScanner<JobsResponse>(
        `/api/jobs${query ? `?${query}` : ""}`,
      )
      const jobs = (data.jobs ?? [])
        .filter(hasConfirmedUsLocation)
        .map(normalizeJobExperience)
        .map(withLogos)

      return NextResponse.json({
        ...data,
        jobs,
        count: jobs.length,
        source: "scanner",
      })
    } catch {
      // Fall through to the packaged snapshot.
    }
  }

  const hours = Number(searchParams.get("lookback_hours")) || null
  const jobs = snapshotJobs()

  return NextResponse.json({
    jobs,
    count: jobs.length,
    scanned_at: null,
    lookback_hours: hours,
    dataset: "main",
    source: "snapshot",
  } satisfies JobsResponse & { source: string })
}
