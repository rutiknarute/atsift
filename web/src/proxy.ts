import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

import { SESSION_COOKIE, readSessionToken } from "@/server/session"

/*
  The gate. Renamed from `middleware` in Next 16 — same job, and it now runs
  on the Node runtime by default, so the session HMAC is verified with real
  `node:crypto` rather than a Web Crypto shim.

  This is the outer perimeter, not the only check. Next's own guidance is that
  a matcher change can silently drop coverage, so every `/api` handler that
  touches data also calls `requireSession` for itself.
*/

const PUBLIC_PATHS = ["/login"]
const PUBLIC_API_PREFIX = "/api/auth/"

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl

  if (PUBLIC_PATHS.includes(pathname) || pathname.startsWith(PUBLIC_API_PREFIX)) {
    return NextResponse.next()
  }

  const session = readSessionToken(request.cookies.get(SESSION_COOKIE)?.value)

  if (session) return NextResponse.next()

  // An API call gets an answer it can parse; a page gets sent to the form.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 })
  }

  const login = new URL("/login", request.url)

  // Come back to where they were headed once they are through.
  if (pathname !== "/") login.searchParams.set("next", `${pathname}${search}`)

  return NextResponse.redirect(login)
}

export const config = {
  /*
    Everything except Next's own asset routes and the app icons. Without the
    exclusions the redirect would swallow the CSS and JS of the login page
    itself.
  */
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|icon.png|apple-icon.png).*)",
  ],
}
