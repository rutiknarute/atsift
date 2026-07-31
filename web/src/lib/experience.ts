import type { Job, JobAnalysis } from "@/lib/types"

const JUNK =
  /^(yes|no|n\/?a|none|null|unknown|not (clearly )?(specified|stated|listed)|analysis unavailable)\.?$/i
const OPTIONAL = /\b(preferred|ideally|nice[- ]to[- ]have|bonus|a plus|desired)\b/i
const REQUIRED = /\b(required|requirement|must|minimum|at least|you have)\b/i
/*
  JDs spell the number out as often as they write it — "at least three years"
  and "two to four years" are as common as "3+ years". Words are only ever
  read as a requirement when a unit is attached, so "two" in ordinary prose
  cannot be mistaken for one.
*/
const NUMBER_WORDS: Record<string, number> = {
  zero: 0,
  one: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
  six: 6,
  seven: 7,
  eight: 8,
  nine: 9,
  ten: 10,
  eleven: 11,
  twelve: 12,
  fifteen: 15,
  twenty: 20,
}

// Longest word first, so "twelve" is not consumed as "two".
const WORDS = Object.keys(NUMBER_WORDS)
  .sort((a, b) => b.length - a.length)
  .join("|")
const NUMBER = `\\d+(?:\\.\\d+)?|${WORDS}`
const UNIT = "years?|yrs?|months?|mos?"

const RANGE = new RegExp(
  `(${NUMBER})\\s*(?:[-–—]|to|through)\\s*(${NUMBER})\\s*\\+?\\s*(${UNIT})?`,
  "gi",
)
const SINGLE = new RegExp(
  `(?:>=?\\s*|(?:at\\s+least|minimum(?:\\s+of)?)\\s+)?(${NUMBER})\\s*\\+?\\s*(${UNIT})\\b`,
  "gi",
)

function spelled(raw: string) {
  return raw.trim().toLowerCase() in NUMBER_WORDS
}

/*
  A digit range can stand alone ("2-4"), but a spelled one needs its unit:
  "one to two" is a phrase, "one to two years" is a requirement.
*/
function usableRange(match: RegExpExecArray): boolean {
  return Boolean(match[3]) || (!spelled(match[1]) && !spelled(match[2]))
}

/*
  Nobody hires on thirty years of experience. A figure past this ceiling is
  the company talking about itself — "a global leader with 50+ years of
  experience" — so the sentence is not a requirement at all.
*/
const MAX_PLAUSIBLE_YEARS = 25

function toNumber(raw: string): number {
  const word = raw.trim().toLowerCase()

  return word in NUMBER_WORDS ? NUMBER_WORDS[word] : Number(word)
}

function asYears(value: number, unit = "years") {
  return /^(month|mo)/i.test(unit)
    ? Math.round((value / 12) * 100) / 100
    : value
}

function valuesInText(value: string): number[] {
  const text = value.trim()

  if (!text || (OPTIONAL.test(text) && !REQUIRED.test(text))) return []

  const values: number[] = []
  const occupied: Array<[number, number]> = []

  for (const match of text.matchAll(RANGE)) {
    if (!usableRange(match)) continue

    values.push(asYears(toNumber(match[1]), match[3]))
    occupied.push([match.index, match.index + match[0].length])
  }

  for (const match of text.matchAll(SINGLE)) {
    if (
      occupied.some(
        ([start, end]) => match.index >= start && match.index < end,
      )
    ) {
      continue
    }

    values.push(asYears(toNumber(match[1]), match[2]))
  }

  if (values.length === 0) {
    const compact = text.match(/^(?:>=?\s*)?(\d+(?:\.\d+)?)\s*\+?$/)
    const compactRange = text.match(
      /^(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*\+?$/,
    )

    if (compactRange) values.push(Number(compactRange[1]))
    else if (compact) values.push(Number(compact[1]))
  }

  const plausible = values.filter(
    (number) => number >= 0 && number <= MAX_PLAUSIBLE_YEARS,
  )
  const branches = text.split(/\bor\b/i)

  if (branches.length > 1) {
    const branchFloors = branches
      .map((branch) => valuesInText(branch))
      .filter((branchValues) => branchValues.length > 0)
      .map((branchValues) => Math.max(...branchValues))

    if (branchFloors.length >= 2) return [Math.min(...branchFloors)]
  }

  return plausible
}

export function inferMinimumYears(...candidates: Array<string | null | undefined>) {
  for (const candidate of candidates) {
    if (!candidate) continue

    const values = valuesInText(candidate)

    if (values.length > 0) return Math.max(...values)
  }

  return null
}

/*
  The requirement, not the sentence it came in.

  A JD says "You bring 5+ years of experience in software development, with a
  focus on data, ML, or AI infrastructure." The only part that decides whether
  a role is worth a click is "5+ years", so that is all this returns.
*/
interface Requirement {
  years: number
  low: number
  high: number | null
  open: boolean
  unit: "years" | "months"
}

const OPEN_ENDED = /\+|\bat\s+least\b|\bminimum\b|>=?/i

function unitOf(raw = "years"): "years" | "months" {
  return /^(month|mo)/i.test(raw) ? "months" : "years"
}

function requirementsInText(text: string): Requirement[] {
  const found: Requirement[] = []
  const occupied: Array<[number, number]> = []

  for (const match of text.matchAll(RANGE)) {
    if (!usableRange(match)) continue

    const unit = unitOf(match[3])

    found.push({
      years: asYears(toNumber(match[1]), match[3]),
      low: toNumber(match[1]),
      high: toNumber(match[2]),
      open: match[0].includes("+"),
      unit,
    })
    occupied.push([match.index, match.index + match[0].length])
  }

  for (const match of text.matchAll(SINGLE)) {
    if (
      occupied.some(
        ([start, end]) => match.index >= start && match.index < end,
      )
    ) {
      continue
    }

    found.push({
      years: asYears(toNumber(match[1]), match[2]),
      low: toNumber(match[1]),
      high: null,
      open: OPEN_ENDED.test(match[0]),
      unit: unitOf(match[2]),
    })
  }

  if (found.length > 0) return found

  // Bare numbers, as the model sometimes returns them: "5+", "2-4".
  const compactRange = text.match(
    /^(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*(\+)?$/,
  )

  if (compactRange) {
    return [
      {
        years: Number(compactRange[1]),
        low: Number(compactRange[1]),
        high: Number(compactRange[2]),
        open: Boolean(compactRange[3]),
        unit: "years",
      },
    ]
  }

  const compact = text.match(/^(>=?\s*)?(\d+(?:\.\d+)?)\s*(\+)?$/)

  if (compact) {
    return [
      {
        years: Number(compact[2]),
        low: Number(compact[2]),
        high: null,
        open: Boolean(compact[1] || compact[3]),
        unit: "years",
      },
    ]
  }

  return []
}

function formatRequirement({ low, high, open, unit }: Requirement): string {
  const noun = unit === "months" ? "month" : "year"
  const plural = high !== null || open || low !== 1 ? "s" : ""

  if (high !== null && high > low) return `${low}–${high} ${noun}${plural}`

  return `${low}${open ? "+" : ""} ${noun}${plural}`
}

export function experienceLabel(analysis?: JobAnalysis): string {
  if (!analysis) return "Not listed"

  const candidates = [
    analysis.experience_years,
    analysis.qualifications,
    analysis.degree,
  ]

  for (const candidate of candidates) {
    const text = (candidate ?? "").trim()

    if (!text || JUNK.test(text)) continue

    const values = valuesInText(text)

    if (values.length === 0) continue

    // `valuesInText` already resolves optional clauses and `or` alternatives,
    // so trust its floor and only borrow the wording from the match it came
    // from — a range stays a range, a "5+" stays open-ended.
    const floor = Math.max(...values)
    const requirements = requirementsInText(text)
    const governing =
      requirements.find((item) => item.years === floor) ?? requirements[0]

    if (governing) return formatRequirement(governing)
  }

  return "Not listed"
}

export function normalizeJobExperience(job: Job): Job {
  const analysis = job.analysis

  if (!analysis) return job

  const label = experienceLabel(analysis)
  const inferred = inferMinimumYears(
    label === "Not listed" ? null : label,
    analysis.qualifications,
    analysis.degree,
    job.description,
  )
  const modelMinimum =
    typeof analysis.minimum_years === "number" &&
    analysis.minimum_years >= 0 &&
    analysis.minimum_years <= MAX_PLAUSIBLE_YEARS
      ? analysis.minimum_years
      : null
  const minimum = inferred ?? modelMinimum

  /*
    The number and the label have to agree, because the experience filter
    reads the number while the card shows the label. A posting matching
    "3+ years" while its tile says "Not listed" is a bug the user sees. So a
    requirement found only in the JD body still gets a label, and a posting
    with no readable requirement carries no number to be filtered on.
  */
  const resolved =
    label !== "Not listed"
      ? label
      : minimum !== null
        ? `${minimum}+ years`
        : "Not listed"

  return {
    ...job,
    analysis: {
      ...analysis,
      experience_years:
        resolved === "Not listed" ? "Not clearly stated." : resolved,
      minimum_years: resolved === "Not listed" ? null : minimum,
    },
  }
}
