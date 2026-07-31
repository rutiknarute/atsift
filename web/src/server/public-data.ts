import "server-only"

import { normalizeJobExperience } from "@/lib/experience"
import type { Job } from "@/lib/types"
import { withLogos } from "@/server/job-logo"

/*
  The packaged snapshot. It exists so the site is browsable with no scanner
  behind it — the deployed build has no Python process to call.
*/

import snapshot from "./jobs-snapshot.json"

interface SnapshotShape {
  jobs?: Job[]
  scanned_at?: string | null
}

const data = snapshot as SnapshotShape
const normalizedJobs = Array.isArray(data.jobs)
  ? data.jobs.map(normalizeJobExperience).map(withLogos)
  : []

/*
  The snapshot is a frozen sample — every posting in it is older than any
  window the UI offers. Applying the live window would therefore always return
  nothing, so the snapshot is served whole and the response is labelled
  `source: "snapshot"` for the UI to say so plainly. Better an honest stale
  list than an empty one that looks like a broken scan.
*/
export function snapshotJobs(): Job[] {
  return normalizedJobs
}

export function snapshotScannedAt(): string | null {
  return data.scanned_at ?? null
}
