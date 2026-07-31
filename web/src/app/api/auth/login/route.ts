import { NextResponse } from "next/server"
import { z } from "zod"

import { allowAttempt, verifyCredentials } from "@/server/auth"
import {
  SESSION_COOKIE,
  createSessionToken,
  sessionCookieOptions,
} from "@/server/session"

const Body = z.object({
  email: z.string().min(1).max(320),
  password: z.string().min(1).max(400),
})

export async function POST(request: Request) {
  const forwarded = request.headers.get("x-forwarded-for")
  const key = forwarded?.split(",")[0]?.trim() || "local"

  // Ten attempts a minute. A person types one; a script wants thousands.
  if (!allowAttempt(`login:${key}`, 10, 60_000)) {
    return NextResponse.json(
      { error: "Too many attempts. Wait a minute and try again." },
      { status: 429 },
    )
  }

  const parsed = Body.safeParse(await request.json().catch(() => null))

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Enter your email and password." },
      { status: 400 },
    )
  }

  let valid: boolean

  try {
    valid = await verifyCredentials(parsed.data.email, parsed.data.password)
  } catch (error) {
    console.error("[auth] configuration problem:", error)

    return NextResponse.json(
      { error: "Sign-in is not configured on the server." },
      { status: 500 },
    )
  }

  /*
    One message for a wrong email and a wrong password. Telling them apart
    tells an attacker which half they already have.
  */
  if (!valid) {
    return NextResponse.json(
      { error: "That email and password do not match." },
      { status: 401 },
    )
  }

  const response = NextResponse.json({ ok: true })

  response.cookies.set(
    SESSION_COOKIE,
    createSessionToken(parsed.data.email.trim().toLowerCase()),
    sessionCookieOptions(),
  )

  return response
}
