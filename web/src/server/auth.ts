import "server-only"

import { scrypt, timingSafeEqual, type ScryptOptions } from "node:crypto"
import { promisify } from "node:util"

/*
  Single-account auth. There is no user table because there is one user: the
  credentials live in the environment, and the password is only ever present
  as a scrypt hash.

  Resend is still here, but it no longer gates sign-in — it carries access
  requests from anyone who lands on the login page and wants in.
*/

// promisify resolves to the 3-argument overload, which drops the cost
// parameters. Name the signature we actually call.
const scryptAsync = promisify(scrypt) as (
  password: string,
  salt: Buffer,
  keylen: number,
  options: ScryptOptions,
) => Promise<Buffer>

/*
  Rate-limit counters, on globalThis so Next's dev hot-reload does not reset
  them between requests.
*/
const store = globalThis as unknown as {
  __beoneAttempts?: Map<string, { count: number; resetAt: number }>
}

const rateLimits = (store.__beoneAttempts ??= new Map())

function constantTimeEquals(a: string, b: string): boolean {
  const left = Buffer.from(a)
  const right = Buffer.from(b)

  if (left.length !== right.length) return false

  return timingSafeEqual(left, right)
}

/**
 * Fixed-window limiter, keyed by whatever the caller considers a client.
 *
 * Enough to stop a script guessing passwords or flooding the owner's inbox;
 * it is not a distributed rate limiter and does not pretend to be. Returns
 * true when the call is allowed.
 */
export function allowAttempt(key: string, limit: number, windowMs: number): boolean {
  const now = Date.now()
  const entry = rateLimits.get(key)

  if (!entry || entry.resetAt <= now) {
    rateLimits.set(key, { count: 1, resetAt: now + windowMs })

    return true
  }

  if (entry.count >= limit) return false

  entry.count += 1

  return true
}

export function configuredEmail(): string {
  return (process.env.AUTH_EMAIL ?? "").trim().toLowerCase()
}

/** True when the credentials match the configured account. */
export async function verifyCredentials(
  email: string,
  password: string,
): Promise<boolean> {
  const expectedEmail = configuredEmail()
  const stored = process.env.AUTH_PASSWORD_HASH ?? ""

  if (!expectedEmail || !stored) {
    throw new Error("AUTH_EMAIL and AUTH_PASSWORD_HASH must both be set.")
  }

  const emailOk = constantTimeEquals(email.trim().toLowerCase(), expectedEmail)

  /*
    scrypt:N:r:p:salt:hash

    Colon-separated, not the conventional `$`, because dotenv expands `$name`
    inside .env values — a `$`-delimited hash silently loses every segment
    that looks like a variable, and arrives here as nonsense. Colons are also
    outside the base64url alphabet, so they cannot appear in salt or hash.
  */
  const [scheme, n, r, p, salt, hash] = stored.split(":")

  if (scheme !== "scrypt" || !salt || !hash) {
    throw new Error("AUTH_PASSWORD_HASH is malformed.")
  }

  const expected = Buffer.from(hash, "base64url")
  const derived = await scryptAsync(
    password,
    Buffer.from(salt, "base64url"),
    expected.length,
    {
      N: Number(n),
      r: Number(r),
      p: Number(p),
      maxmem: 64 * 1024 * 1024,
    },
  )

  const passwordOk =
    derived.length === expected.length && timingSafeEqual(derived, expected)

  // Both checks always run, so a wrong email and a wrong password cost the
  // same time and are indistinguishable from outside.
  return emailOk && passwordOk
}

/**
 * Mail the owner someone's request for access.
 *
 * Throws when Resend rejects it, so the page can say the request did not go
 * through rather than claiming a send that never happened.
 */
export async function sendAccessRequest(
  from: string,
  note: string,
): Promise<void> {
  const key = process.env.RESEND_API_KEY

  if (!key) throw new Error("RESEND_API_KEY is not set.")

  const owner = configuredEmail()

  if (!owner) throw new Error("AUTH_EMAIL is not set.")

  const sender = process.env.AUTH_EMAIL_FROM ?? "ATSift <onboarding@resend.dev>"

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: sender,
      to: [owner],
      // Replying goes straight back to whoever asked.
      reply_to: from,
      subject: `ATSift access request from ${from}`,
      text: `${from} is asking for access to ATSift.\n\n${note || "(no message)"}\n\nReply to this email to reach them.`,
      html: accessRequestEmail(from, note),
    }),
  })

  if (!response.ok) {
    const detail = await response.text().catch(() => "")

    throw new Error(
      `Resend rejected the send (${response.status}): ${detail.slice(0, 300)}`,
    )
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

function accessRequestEmail(from: string, note: string): string {
  // Both values come from a stranger, so both are escaped before they land in
  // the owner's inbox.
  const safeFrom = escapeHtml(from)
  const safeNote = escapeHtml(note || "(no message)").replace(/\n/g, "<br>")

  return `<!doctype html>
<html>
  <body style="margin:0;background:#f5f7fc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:32px 16px">
    <table role="presentation" cellpadding="0" cellspacing="0" style="max-width:460px;margin:0 auto;background:#ffffff;border:1px solid #dae2f0;border-radius:14px">
      <tr>
        <td style="padding:32px">
          <p style="margin:0;font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:#5d6879">ATSift</p>
          <h1 style="margin:12px 0 0;font-size:20px;line-height:1.3;color:#080c14">Someone wants access</h1>
          <p style="margin:16px 0 0;font-size:14px;line-height:1.6;color:#414b5e"><strong style="color:#080c14">${safeFrom}</strong> asked for access to ATSift.</p>
          <div style="margin:20px 0 0;background:#eef2fb;border-radius:12px;padding:16px;font-size:14px;line-height:1.6;color:#414b5e">${safeNote}</div>
          <p style="margin:20px 0 0;font-size:13px;line-height:1.6;color:#5d6879">Reply to this email to reach them directly.</p>
        </td>
      </tr>
    </table>
  </body>
</html>`
}
