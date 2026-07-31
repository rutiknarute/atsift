import { NextResponse } from "next/server"

import { fetchScanner, scannerAvailable } from "@/server/scanner-client"
import { requireSession } from "@/server/guard"

export async function POST() {
  const denied = await requireSession()

  if (denied) return denied

  if (!(await scannerAvailable())) {
    return NextResponse.json({ stopping: false }, { status: 503 })
  }

  try {
    const data = await fetchScanner("/api/scan/stop", { method: "POST" })

    return NextResponse.json(data)
  } catch {
    return NextResponse.json(
      { error: "Could not stop the scan." },
      { status: 502 },
    )
  }
}
