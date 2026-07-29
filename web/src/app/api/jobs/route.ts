import { NextResponse } from "next/server"

import { fetchScanner, scannerAvailable } from "@/server/scanner-client"
import { snapshotJobs } from "@/server/public-data"
import type { JobsResponse } from "@/lib/types"

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const query = searchParams.toString()

  if (await scannerAvailable()) {
    try {
      const data = await fetchScanner<JobsResponse>(
        `/api/jobs${query ? `?${query}` : ""}`,
      )

      return NextResponse.json({ ...data, source: "scanner" })
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
