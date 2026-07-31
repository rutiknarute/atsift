import { NextResponse } from "next/server"
import { z } from "zod"

import { allowAttempt, sendAccessRequest } from "@/server/auth"

const Body = z.object({
  email: z.email().max(320),
  note: z.string().max(600).optional(),
})

/*
  Open to anyone who reaches the login page — that is the point, it is how a
  stranger asks the owner for access. Being open is also why it is the most
  abusable route here: it puts text in someone's inbox. Hence the tight limit
  and the capped note length.
*/
export async function POST(request: Request) {
  const forwarded = request.headers.get("x-forwarded-for")
  const key = forwarded?.split(",")[0]?.trim() || "local"

  if (!allowAttempt(`request:${key}`, 3, 60 * 60_000)) {
    return NextResponse.json(
      { error: "You have already sent a request. Give it some time." },
      { status: 429 },
    )
  }

  const parsed = Body.safeParse(await request.json().catch(() => null))

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Enter a valid email address." },
      { status: 400 },
    )
  }

  try {
    await sendAccessRequest(parsed.data.email.trim(), parsed.data.note?.trim() ?? "")
  } catch (error) {
    console.error("[auth] could not send the access request:", error)

    return NextResponse.json(
      { error: "Could not send that request. Try again later." },
      { status: 502 },
    )
  }

  return NextResponse.json({ ok: true })
}
