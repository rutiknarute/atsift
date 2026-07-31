import { createHmac, timingSafeEqual } from "node:crypto"

/*
  Stateless signed sessions.

  The cookie carries its own claims and an HMAC over them, so a restart of the
  dev server does not sign you out — unlike the login challenge, which is
  deliberately in-memory and short-lived (see `auth.ts`).

  Nothing secret lives in the payload. It is signed, not encrypted: anyone
  holding the cookie can read the email and expiry, but cannot change either
  without `AUTH_SECRET`.
*/

export const SESSION_COOKIE = "beone_session"

// Long enough that a personal tool does not nag; short enough that a stolen
// laptop is not a permanent grant.
export const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30

/*
  Times are epoch *milliseconds*, not the seconds a JWT would use. Nothing
  else consumes this token, and second-granularity made revocation ambiguous:
  a token minted in the same second as a sign-out compared equal to the
  cut-off and survived it.
*/
interface SessionClaims {
  email: string
  /** Issued at, epoch milliseconds. */
  iat: number
  /** Expiry, epoch milliseconds. */
  exp: number
}

/*
  Signing out has to actually end the session.

  A signed cookie cannot revoke itself — deleting it from the browser leaves
  the token valid for anyone who copied it. So sign-out records a cut-off and
  every token issued before it is refused. One account means "revoke mine" and
  "revoke all" are the same instruction.

  This lives in memory, so a server restart forgets the cut-off and a token
  captured before sign-out would work again until it expires. Persisting it
  would mean a writable disk, which the deploy target does not guarantee.
*/
const revocation = globalThis as unknown as { __beoneMinIat?: number }

export function revokeAllSessions(): void {
  revocation.__beoneMinIat = Date.now()
}

function secret(): string {
  const value = process.env.AUTH_SECRET

  if (!value) {
    throw new Error("AUTH_SECRET is not set — sessions cannot be signed.")
  }

  return value
}

function sign(payload: string): string {
  return createHmac("sha256", secret()).update(payload).digest("base64url")
}

/** Compare without leaking, via timing, how much of the signature matched. */
function signatureMatches(expected: string, received: string): boolean {
  const a = Buffer.from(expected)
  const b = Buffer.from(received)

  if (a.length !== b.length) return false

  return timingSafeEqual(a, b)
}

export function createSessionToken(email: string): string {
  const now = Date.now()
  const claims: SessionClaims = {
    email,
    iat: now,
    exp: now + SESSION_MAX_AGE_SECONDS * 1000,
  }
  const payload = Buffer.from(JSON.stringify(claims)).toString("base64url")

  return `${payload}.${sign(payload)}`
}

/**
 * The claims if the token is intact and unexpired, otherwise null.
 *
 * Every failure returns null rather than throwing — a malformed cookie is an
 * ordinary thing for a browser to send, not an error condition.
 */
export function readSessionToken(token: string | undefined): SessionClaims | null {
  if (!token) return null

  const [payload, signature] = token.split(".")

  if (!payload || !signature) return null
  if (!signatureMatches(sign(payload), signature)) return null

  try {
    const claims = JSON.parse(
      Buffer.from(payload, "base64url").toString("utf8"),
    ) as SessionClaims

    if (typeof claims?.email !== "string") return null
    if (typeof claims?.exp !== "number") return null
    if (typeof claims?.iat !== "number") return null

    if (claims.exp <= Date.now()) return null

    // Issued at or before the last sign-out, so it no longer counts. `<=`
    // rather than `<` so a cut-off can never be tied with, and survived by,
    // the very token it was meant to kill.
    if (claims.iat <= (revocation.__beoneMinIat ?? 0)) return null

    return claims
  } catch {
    return null
  }
}

/** The cookie options every place that sets the session must agree on. */
export function sessionCookieOptions(maxAge: number = SESSION_MAX_AGE_SECONDS) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  }
}
