import { NextResponse } from "next/server"

import { allowAttempt } from "@/server/auth"
import {
  DEMO_MAX_AGE_SECONDS,
  SESSION_COOKIE,
  createSessionToken,
  sessionCookieOptions,
} from "@/server/session"

/*
  Open by design: this is the "let anyone look around" button, so it takes no
  credentials.

  What it hands out is deliberately not an owner session — the token carries
  role "demo", and every route that starts a scan, writes to the store, or
  spends OpenRouter credits checks for "owner" instead. It also expires in
  hours rather than a month.
*/
export async function POST(request: Request) {
  const forwarded = request.headers.get("x-forwarded-for")
  const key = forwarded?.split(",")[0]?.trim() || "local"

  // Nobody needs a fresh demo session ten times a minute; this only stops
  // someone minting cookies in a loop.
  if (!allowAttempt(`demo:${key}`, 10, 10 * 60_000)) {
    return NextResponse.json(
      { error: "Too many demo sessions. Wait a few minutes." },
      { status: 429 },
    )
  }

  const response = NextResponse.json({ ok: true })

  response.cookies.set(
    SESSION_COOKIE,
    createSessionToken("demo@atsift.app", "demo"),
    sessionCookieOptions(DEMO_MAX_AGE_SECONDS),
  )

  return response
}
