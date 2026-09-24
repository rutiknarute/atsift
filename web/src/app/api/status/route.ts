import { NextResponse } from "next/server"

import { fetchScanner, scannerAvailable } from "@/server/scanner-client"
import type { ScanStatus } from "@/lib/types"
import { requireSession } from "@/server/guard"

const IDLE: ScanStatus = {
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

export async function GET() {
  const denied = await requireSession()

  if (denied) return denied

  if (!(await scannerAvailable())) {
    return NextResponse.json({ ...IDLE, scanner_available: false })
  }

  try {
    const data = await fetchScanner<ScanStatus>("/api/status")

    return NextResponse.json({ ...data, scanner_available: true })
  } catch {
    return NextResponse.json({ ...IDLE, scanner_available: false })
  }
}
