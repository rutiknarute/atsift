import { NextResponse } from "next/server"

import { fetchScanner, scannerAvailable } from "@/server/scanner-client"

export async function POST() {
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
