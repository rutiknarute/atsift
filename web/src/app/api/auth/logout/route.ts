import { NextResponse } from "next/server"

import { SESSION_COOKIE, revokeAllSessions } from "@/server/session"

export async function POST() {
  // Clearing the cookie only disarms this browser. Revoking makes the token
  // itself useless, including any copy of it.
  revokeAllSessions()

  const response = NextResponse.json({ ok: true })

  response.cookies.delete(SESSION_COOKIE)

  return response
}
