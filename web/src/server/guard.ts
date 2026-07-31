import "server-only"

import { cookies } from "next/headers"
import { NextResponse } from "next/server"

import {
  SESSION_COOKIE,
  readSessionToken,
  type SessionRole,
} from "@/server/session"

/*
  Defence in depth for the route handlers.

  The proxy already turns away anonymous requests, but Next's own docs warn
  that a matcher edit — or a refactor that moves a handler — can quietly
  remove that cover. These handlers reach the scanner and the OpenRouter key,
  so each one re-checks rather than trusting the perimeter.
*/

export async function sessionRole(): Promise<SessionRole | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value

  return readSessionToken(token)?.role ?? null
}

/**
 * Any signed-in caller, demo included.
 *
 * Returns a 401 response to hand straight back, or null to proceed.
 */
export async function requireSession(): Promise<NextResponse | null> {
  return (await sessionRole()) ? null : unauthorized()
}

/**
 * The owner only.
 *
 * For anything that spends money or changes state. Anyone can mint a demo
 * session from the login page, so a demo session must not be able to start a
 * scan or write to the store — otherwise the "give anybody access" button
 * hands strangers the keys.
 */
export async function requireOwner(): Promise<NextResponse | null> {
  const role = await sessionRole()

  if (role === "owner") return null

  if (role === "demo") {
    return NextResponse.json(
      { error: "The demo account can browse results but cannot do this." },
      { status: 403 },
    )
  }

  return unauthorized()
}

function unauthorized() {
  return NextResponse.json({ error: "Not signed in." }, { status: 401 })
}
