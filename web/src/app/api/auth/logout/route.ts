import { NextResponse } from "next/server"

import { sessionRole } from "@/server/guard"
import { SESSION_COOKIE, revokeAllSessions } from "@/server/session"

export async function POST() {
  /*
    Revocation is global — it invalidates every token issued before now. That
    is right for the owner ("sign me out everywhere") and wrong for a demo
    visitor, who would otherwise sign the owner out by leaving. A demo
    sign-out just drops its own cookie.
  */
  if ((await sessionRole()) === "owner") revokeAllSessions()

  const response = NextResponse.json({ ok: true })

  response.cookies.delete(SESSION_COOKIE)

  return response
}
