import "server-only"

/*
  The one place that talks to the Flask scanner.

  Availability is decided by an actual health probe, never by whether a URL is
  configured — a URL that merely parses is not a reachable scanner.
*/

const HEALTH_TTL_MS = 10_000

let healthCache: { ok: boolean; at: number } | null = null

export function scannerBaseUrl(): string | null {
  const raw = process.env.SCANNER_API_BASE_URL?.trim()

  if (!raw) return null

  try {
    return new URL(raw).origin
  } catch {
    return null
  }
}

function authHeaders(): Record<string, string> {
  const token = process.env.SCANNER_API_TOKEN?.trim()

  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function fetchScanner<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 20_000,
): Promise<T> {
  const base = scannerBaseUrl()

  if (!base) throw new Error("No scanner configured.")

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(`${base}${path}`, {
      ...init,
      cache: "no-store",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(init.headers ?? {}),
      },
    })

    if (!response.ok) {
      throw new Error(`Scanner responded ${response.status}`)
    }

    return (await response.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

export async function scannerAvailable(): Promise<boolean> {
  const base = scannerBaseUrl()

  if (!base) return false

  const now = Date.now()

  if (healthCache && now - healthCache.at < HEALTH_TTL_MS) {
    return healthCache.ok
  }

  let ok = false

  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 2_500)

    const response = await fetch(`${base}/api/health`, {
      cache: "no-store",
      signal: controller.signal,
    })

    clearTimeout(timer)
    ok = response.ok
  } catch {
    ok = false
  }

  healthCache = { ok, at: now }

  return ok
}
