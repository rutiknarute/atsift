import { NextResponse } from "next/server"
import catalogMeta from "@/server/catalog-meta.json"

import { fetchScanner, scannerAvailable } from "@/server/scanner-client"
import type { ScannerMeta } from "@/lib/types"
import { requireSession, sessionRole } from "@/server/guard"

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
  ...catalogMeta,
  lookback_options: [1, 2, 4, 6, 12, 24, 48, 72],
  default_lookback_hours: 24,
  max_lookback_hours: 72,
}

export async function GET() {
  const denied = await requireSession()

  if (denied) return denied

  // The dashboard needs the role to decide whether to offer a Run button at
  // all. Showing one to a demo visitor would only produce a 403 on click.
  const role = await sessionRole()

  if (!(await scannerAvailable())) {
    return NextResponse.json({ ...FALLBACK, scanner_available: false, role })
  }

  try {
    const data = await fetchScanner<ScannerMeta>("/api/meta")

    return NextResponse.json({ ...data, scanner_available: true, role })
  } catch {
    return NextResponse.json({ ...FALLBACK, scanner_available: false, role })
  }
}
