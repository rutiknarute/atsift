import { NextResponse } from "next/server"

import { fetchScanner, scannerAvailable } from "@/server/scanner-client"
import { requireOwner } from "@/server/guard"

export async function POST(request: Request) {
  const denied = await requireOwner()

  if (denied) return denied

  if (!(await scannerAvailable())) {
    return NextResponse.json(
      { error: "The scanner is not reachable right now." },
      { status: 503 },
    )
  }

  const body = await request.json().catch(() => ({}))

  try {
    const data = await fetchScanner("/api/scan", {
      method: "POST",
      body: JSON.stringify(body),
    })

    return NextResponse.json(data)
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Could not start the scan."

    return NextResponse.json({ error: message }, { status: 502 })
  }
}
