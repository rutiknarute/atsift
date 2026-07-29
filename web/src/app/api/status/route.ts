import { NextResponse } from "next/server"

import { fetchScanner, scannerAvailable } from "@/server/scanner-client"
import type { ScanStatus } from "@/lib/types"

const IDLE: ScanStatus = {
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

export async function GET() {
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
