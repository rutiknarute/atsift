import type { Job } from "@/lib/types"

/*
  Hard blockers, found in the posting's own words.

  An F-1/OPT candidate is wasting an application on a role that demands US
  citizenship, a security clearance, a green card, or that says outright it
  will not sponsor. The local model is too small to be trusted with that call,
  so this reads the text directly and only fires on explicit wording.

  Everything is decided per clause. "Not eligible for visa sponsorship
  (H-1B, L-1, O-1 or CPT/OPT)" and "Eligible for F-1 OPT sponsorship" differ
  only by a negation, and splitting first keeps one sentence's negation from
  colouring its neighbour.
*/

export type BlockerKind = "clearance" | "citizenship" | "sponsorship"

export interface Blocker {
  kind: BlockerKind
  message: string
}

// Postings gloss the country mid-phrase: "a United States (U.S.) citizen".
const US = "(?:u\\.?\\s?s\\.?a?|united states)(?:\\s*\\([^)]{1,20}\\))?"

const CLEARANCE = [
  /\b(?:ts\s*\/\s*sci|top[\s-]?secret|security|dod|d\.o\.d\.|public trust|secret|polygraph)\s+clearance\b/i,
  /\bclearance\b[^.]{0,40}\b(?:required|active|obtain|maintain)\b/i,
  /\b(?:active|obtain|maintain)\b[^.]{0,40}\bclearance\b/i,
  /\bts\s*\/\s*sci\b/i,
]

const CITIZENSHIP = [
  new RegExp(`\\b${US}\\s+citizenship\\b`, "i"),
  new RegExp(`\\bmust\\s+be\\s+(?:an?\\s+)?${US}\\s+citizen\\b`, "i"),
  new RegExp(`\\b${US}\\s+citizens?\\s+only\\b`, "i"),
  new RegExp(`\\brestricted\\s+to\\s+${US}\\s+citizens?\\b`, "i"),
  new RegExp(`\\bbe\\s+a\\s+${US}\\s+citizen\\b`, "i"),
  /\bcitizenship\s+(?:is\s+)?required\b/i,
  // A bare mention is enough. Postings do not name citizenship unless it
  // matters, and the one benign phrasing is handled by the escape below.
  new RegExp(`\\b${US}\\s+citizens?\\b`, "i"),
]

const PERMANENT_RESIDENT = [
  /\bgreen\s?card\b/i,
  /\b(?:lawful\s+)?permanent\s+resident\b/i,
]

const NO_SPONSORSHIP = [
  /\b(?:not|non-?|in)\s*eligible\s+for\b[^.]{0,60}\bsponsorship\b/i,
  /\bineligible\s+for\b[^.]{0,60}\bsponsorship\b/i,
  /\bunable\s+to\b[^.]{0,40}\bsponsor/i,
  /\b(?:do(?:es)?\s+not|will\s+not|won'?t|cannot|can'?t)\b[^.]{0,40}\bsponsor/i,
  /\bwithout\b[^.]{0,40}\bsponsorship\b/i,
  /\bno\s+(?:current\s+or\s+future\s+)?(?:visa\s+|employment\s+|immigration\s+)?sponsorship\b/i,
  /\bnot\s+open\s+to\b[^.]{0,40}\bsponsorship\b/i,
  /\bsponsorship\s+(?:is\s+)?not\s+(?:available|offered|provided)\b/i,
]

/*
  "Must be a U.S. citizen or have a valid work authorization" is not a
  citizenship requirement — the second branch is exactly what an OPT candidate
  has. Only the clause offering that alternative is spared.
*/
const WORK_AUTHORIZATION_ALTERNATIVE = new RegExp(
  "\\bcitizen[^.]{0,80}\\bor\\b[^.]{0,80}" +
    "(?:valid\\s+work\\s+authorization|work\\s+authorization|" +
    "authorized\\s+to\\s+work|work\\s+visa)",
  "i",
)

function clauses(text: string): string[] {
  return text
    .replace(/<[^>]+>/g, " ")
    .split(/[\n\r]+|(?<=[.!?;:])\s+|[•●▪]/)
    .map((clause) => clause.trim())
    .filter(Boolean)
}

function matchesAny(clause: string, patterns: RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(clause))
}

export function detectBlocker(job: Job): Blocker | null {
  const analysis = job.analysis
  const sources = [
    job.description,
    analysis?.eligibility,
    analysis?.qualifications,
    analysis?.degree,
    analysis?.opt_blocking_line,
  ]

  let citizenship = false
  let residency = false
  let clearance = false
  let sponsorship = false

  for (const source of sources) {
    if (!source) continue

    for (const clause of clauses(source)) {
      if (matchesAny(clause, CLEARANCE)) clearance = true

      if (
        matchesAny(clause, CITIZENSHIP) &&
        !WORK_AUTHORIZATION_ALTERNATIVE.test(clause)
      ) {
        citizenship = true
      }

      if (
        matchesAny(clause, PERMANENT_RESIDENT) &&
        !WORK_AUTHORIZATION_ALTERNATIVE.test(clause)
      ) {
        residency = true
      }

      if (matchesAny(clause, NO_SPONSORSHIP)) sponsorship = true
    }
  }

  // Most disqualifying first — a clearance role is closed to OPT no matter
  // what the rest of the posting says.
  if (clearance) {
    return {
      kind: "clearance",
      message: "Requires a US security clearance — closed to F-1/OPT",
    }
  }

  if (citizenship || residency) {
    return {
      kind: "citizenship",
      message:
        citizenship && residency
          ? "Requires US citizenship or a green card"
          : citizenship
            ? "Requires US citizenship"
            : "Requires permanent residency (green card)",
    }
  }

  if (sponsorship) {
    return {
      kind: "sponsorship",
      message: "No visa sponsorship — F-1 OPT/STEM OPT not accepted",
    }
  }

  return null
}
