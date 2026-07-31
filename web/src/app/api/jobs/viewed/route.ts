import { NextResponse } from "next/server"

import { fetchScanner, scannerAvailable } from "@/server/scanner-client"
import { requireSession } from "@/server/guard"

export async function POST(request: Request) {
  const denied = await requireSession()

  if (denied) return denied

  const body = await request.json().catch(() => ({}))

  if (!body?.uid) {
    return NextResponse.json({ error: "uid is required" }, { status: 400 })
  }

  // With no scanner the click still counts locally; there is just nowhere
  // durable to record it, and failing the request would be noise.
  if (!(await scannerAvailable())) {
    return NextResponse.json({ ok: true, persisted: false })
  }

  try {
    const data = await fetchScanner("/api/jobs/viewed", {
      method: "POST",
      body: JSON.stringify(body),
    })

    return NextResponse.json({ ...(data as object), persisted: true })
  } catch {
    return NextResponse.json({ ok: true, persisted: false })
  }
}
