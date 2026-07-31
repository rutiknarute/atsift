import "server-only"

import { cookies } from "next/headers"
import { NextResponse } from "next/server"

import { SESSION_COOKIE, readSessionToken } from "@/server/session"

/*
  Defence in depth for the route handlers.

  The proxy already turns away anonymous requests, but Next's own docs warn
  that a matcher edit — or a refactor that moves a handler — can quietly
  remove that cover. These handlers reach the scanner and the OpenRouter key,
  so each one re-checks rather than trusting the perimeter.

  Returns a 401 response to hand straight back, or null when the caller may
  proceed.
*/
export async function requireSession(): Promise<NextResponse | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value

  if (readSessionToken(token)) return null

  return NextResponse.json({ error: "Not signed in." }, { status: 401 })
}
