import "server-only"

import {
  createOpenRouter,
  type OpenRouterProvider,
} from "@openrouter/ai-sdk-provider"
import { ToolLoopAgent, stepCountIs, tool } from "ai"
import { z } from "zod"

import type { Job } from "@/lib/types"
import { snapshotJobs } from "@/server/public-data"
import { fetchScanner, scannerAvailable } from "@/server/scanner-client"

/*
  The AI Job Scout.

  Read-only by construction: its one tool searches jobs that have already been
  scanned. The model can rank and explain, but it cannot invent a posting or a
  URL, and it cannot trigger a scan.
*/

const DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
const DEFAULT_SEARCH_HOURS = 24
const MAX_SEARCH_HOURS = 72

const STOP_WORDS = new Set([
  "a", "an", "and", "at", "entry", "entry-level", "for", "grad", "graduate",
  "in", "job", "jobs", "junior", "level", "me", "new", "of", "or", "role",
  "roles", "the", "to", "with", "find", "show", "any", "some", "please",
])

let provider: OpenRouterProvider | null = null

function getProvider() {
  const apiKey = process.env.OPENROUTER_API_KEY?.trim()

  if (!apiKey) {
    throw new Error("OPENROUTER_API_KEY is required for the AI Job Scout.")
  }

  provider ??= createOpenRouter({
    apiKey,
    appName: "ATSift",
    compatibility: "strict",
  })

  return provider
}

function terms(value: string): string[] {
  return [
    ...new Set(
      value
        .toLowerCase()
        .replace(/[^a-z0-9+#.\-/\s]/g, " ")
        .split(/\s+/)
        .map((term) => term.trim())
        .filter((term) => term.length > 1 && !STOP_WORDS.has(term)),
    ),
  ]
}

function searchableText(job: Job): string {
  return [
    job.title,
    job.company,
    job.location,
    job.team,
    ...(job.category_labels ?? []),
    ...(job.analysis?.key_tech_skills ?? []),
    ...(job.analysis?.ats_keywords ?? []),
    job.analysis?.degree ?? "",
    job.analysis?.qualifications ?? "",
  ]
    .join(" ")
    .toLowerCase()
}

function safeUrl(job: Job): string {
  try {
    const url = new URL(job.url)

    return url.protocol === "https:" || url.protocol === "http:"
      ? url.toString()
      : ""
  } catch {
    return ""
  }
}

function compact(job: Job, matched: string[]) {
  return {
    uid: job.uid,
    title: job.title,
    company: job.company,
    location: job.location,
    ats: job.ats,
    ageHours: job.age_hours,
    minimumYears: job.analysis?.minimum_years ?? null,
    optEligible: job.analysis?.opt_eligible ?? "UNKNOWN",
    skills: [
      ...new Set([
        ...(job.analysis?.key_tech_skills ?? []),
        ...(job.analysis?.ats_keywords ?? []),
      ]),
    ].slice(0, 8),
    matchedTerms: matched,
    applyUrl: safeUrl(job),
  }
}

async function jobsInWindow(hours: number): Promise<Job[]> {
  if (await scannerAvailable()) {
    try {
      const data = await fetchScanner<{ jobs?: Job[] }>(
        `/api/jobs?lookback_hours=${hours}&dataset=main`,
      )

      if (Array.isArray(data.jobs)) return data.jobs
    } catch {
      // Fall through to the packaged snapshot.
    }
  }

  return snapshotJobs()
}

const searchJobs = tool({
  description:
    "Search jobs ATSift has already scanned. Infer role, skills, location, " +
    "experience limit and OPT need from the request. This is the only source " +
    "of job facts and URLs — never state a job or link that did not come from it.",
  inputSchema: z.object({
    keywords: z
      .string()
      .max(160)
      .describe("Role titles or skills, e.g. 'frontend react'. Empty for any."),
    location: z
      .string()
      .max(100)
      .describe("City, state, country, or 'remote'. Empty for any."),
    postedWithinHours: z
      .number()
      .min(1)
      .max(MAX_SEARCH_HOURS)
      .default(DEFAULT_SEARCH_HOURS)
      .describe("Posting age in hours, 1-72. Convert days to hours."),
    maxExperienceYears: z
      .number()
      .min(0)
      .max(20)
      .nullable()
      .default(null)
      .describe("Max stated minimum experience, or null for no limit."),
    optEligibleOnly: z
      .boolean()
      .default(false)
      .describe("True only when the user asks for OPT-friendly roles."),
    limit: z.number().min(1).max(10).default(5).describe("How many to return."),
  }),
  execute: async ({
    keywords,
    location,
    postedWithinHours,
    maxExperienceYears,
    optEligibleOnly,
    limit,
  }) => {
    const hours = Math.max(1, Math.min(MAX_SEARCH_HOURS, postedWithinHours))
    const pool = await jobsInWindow(hours)
    const keywordTerms = terms(keywords)
    const locationTerms = terms(location)

    const ranked = pool
      .map((job) => {
        const haystack = searchableText(job)
        const title = job.title.toLowerCase()

        const matched = keywordTerms.filter((term) => haystack.includes(term))
        const locationHit =
          locationTerms.length === 0 ||
          locationTerms.some((term) => job.location.toLowerCase().includes(term))

        // Title hits are worth more than a mention buried in the description.
        const score =
          matched.length +
          matched.filter((term) => title.includes(term)).length * 2

        return { job, matched, locationHit, score }
      })
      .filter(({ job, matched, locationHit }) => {
        if (!locationHit) return false
        if (keywordTerms.length > 0 && matched.length === 0) return false

        if (optEligibleOnly && job.analysis?.opt_eligible === "NO") return false

        if (maxExperienceYears !== null) {
          const minimum = job.analysis?.minimum_years

          if (typeof minimum === "number" && minimum > maxExperienceYears) {
            return false
          }
        }

        return true
      })
      .sort(
        (a, b) =>
          b.score - a.score ||
          (a.job.age_hours ?? Infinity) - (b.job.age_hours ?? Infinity),
      )
      .slice(0, limit)

    return {
      searchedWithinHours: hours,
      totalInWindow: pool.length,
      matchCount: ranked.length,
      jobs: ranked.map(({ job, matched }) => compact(job, matched)),
    }
  },
})

const SYSTEM = `
You are ATSift's Job Scout. You help an F-1/OPT job seeker find fresh roles.

Rules:
- Always call searchJobs before answering anything about jobs. Never answer
  from memory.
- Only mention jobs the tool returned. Never invent a company, title, or URL.
- If the tool returns nothing, say so plainly and suggest widening the
  timeframe or loosening the keywords. Do not pad with guesses.
- Lead with the best match. For each: title, company, location, how old the
  posting is, and the apply link.
- Be brief. Short lines, no long paragraphs, no preamble.
- If a role is marked optEligible "NO", say it blocks OPT candidates.
`.trim()

export function createJobScout() {
  const model = process.env.OPENROUTER_MODEL?.trim() || DEFAULT_MODEL

  return new ToolLoopAgent({
    model: getProvider()(model),
    instructions: SYSTEM,
    tools: { searchJobs },
    stopWhen: stepCountIs(4),
  })
}
