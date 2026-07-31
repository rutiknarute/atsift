import { NextResponse } from "next/server"

import { fetchScanner, scannerAvailable } from "@/server/scanner-client"
import type { ScannerMeta } from "@/lib/types"
import { requireSession } from "@/server/guard"

// Mirrors scanner/boolean_search.py and scanner/config.py, so the controls
// still render with no scanner reachable.
const FALLBACK: ScannerMeta = {
  categories: [
    { id: "software", label: "Software" },
    { id: "new_grad", label: "New Grad" },
    { id: "data_analyst", label: "Data Analyst" },
    { id: "data_engineer", label: "Data Engineer" },
    { id: "ai_ml", label: "AI / ML" },
    { id: "gtm", label: "GTM" },
  ],
  datasets: [
    { id: "main", label: "Greenhouse · Ashby · Lever · SmartRecruiters · Workable", count: 17167 },
    { id: "workday", label: "Workday", count: 1097 },
  ],
  lookback_options: [6, 12, 24, 48, 72],
  default_lookback_hours: 24,
  max_lookback_hours: 72,
}

export async function GET() {
  const denied = await requireSession()

  if (denied) return denied

  if (!(await scannerAvailable())) {
    return NextResponse.json({ ...FALLBACK, scanner_available: false })
  }

  try {
    const data = await fetchScanner<ScannerMeta>("/api/meta")

    return NextResponse.json({ ...data, scanner_available: true })
  } catch {
    return NextResponse.json({ ...FALLBACK, scanner_available: false })
  }
}
