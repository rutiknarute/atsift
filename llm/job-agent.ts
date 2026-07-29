import "server-only"

import { createOpenRouter, type OpenRouterProvider } from "@openrouter/ai-sdk-provider"
import { ToolLoopAgent, stepCountIs, tool } from "ai"
import { z } from "zod"

import type { Job } from "@/lib/types"
import { jobsForDataset } from "@/server/public-data"
import { fetchScanner } from "@/server/scanner-client"

const DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct"
const DEFAULT_SEARCH_HOURS = 12
const MAX_SEARCH_HOURS = 72
const STOP_WORDS = new Set([
  "a",
  "an",
  "and",
  "at",
  "entry",
  "entry-level",
  "for",
  "grad",
  "graduate",
  "in",
  "job",
  "jobs",
  "junior",
  "level",
  "me",
  "new",
  "of",
  "or",
  "role",
  "roles",
  "the",
  "to",
  "with",
])

let openRouterProvider: OpenRouterProvider | null = null

function getOpenRouterProvider() {
  const apiKey = process.env.OPENROUTER_API_KEY?.trim()

  if (!apiKey) {
    throw new Error("OPENROUTER_API_KEY is required for Llama Online.")
  }

  if (!openRouterProvider) {
    openRouterProvider = createOpenRouter({
      apiKey,
      appName: "ATSift",
      compatibility: "strict",
    })
  }

  return openRouterProvider
}

function normalizedTerms(value: string) {
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

function jobSearchText(job: Job) {
  return [
    job.title,
    job.company,
    job.location,
    job.team,
    ...job.categories,
    ...job.analysis.key_tech_skills,
    ...job.analysis.ats_keywords,
    job.analysis.degree,
    job.analysis.qualifications,
    job.analysis.eligibility,
  ]
    .join(" ")
    .toLowerCase()
}

function safeJobUrl(job: Job) {
  const candidate = job.apply_url || job.job_url

  try {
    const url = new URL(candidate)
    return url.protocol === "https:" || url.protocol === "http:"
      ? url.toString()
      : ""
  } catch {
    return ""
  }
}

function compactJob(job: Job, matchedTerms: string[]) {
  return {
    uid: job.uid,
    title: job.title,
    company: job.company,
    location: job.location,
    source: job.source,
    publishedAt: job.first_published_at,
    minimumYears: job.analysis.minimum_years,
    optEligible: job.analysis.opt_eligible,
    skills: [
      ...new Set([
        ...job.analysis.key_tech_skills,
        ...job.analysis.ats_keywords,
      ]),
    ].slice(0, 8),
    matchedTerms,
    applyUrl: safeJobUrl(job),
  }
}

async function currentJobs(hours: number) {
  const scannerResponse = await fetchScanner(
    `/api/jobs?lookback_hours=${hours}&dataset=main`,
  )

  if (scannerResponse?.ok) {
    try {
      const jobs = await scannerResponse.json()

      if (Array.isArray(jobs)) return jobs as Job[]
    } catch {
      // Fall back to the packaged snapshot when a scanner response is malformed.
    }
  }

  return jobsForDataset("main", hours)
}

const searchJobs = tool({
  description:
    "Search ATSift's latest scraped jobs. Infer role, skills, geography, experience, OPT needs, and timeframe from the prompt. Use 12 hours when no timeframe was requested. This is the only source of job facts and URLs.",
  inputSchema: z.object({
    keywords: z
      .string()
      .max(160)
      .describe("Role titles or skills, such as 'frontend react' or 'data analyst SQL'. Use an empty string for any role."),
    location: z
      .string()
      .max(100)
      .describe("City, state, country, or 'remote'. Use an empty string for any location."),
    postedWithinHours: z
      .string()
      .max(3)
      .optional()
      .default(String(DEFAULT_SEARCH_HOURS))
      .describe("Requested posting age in hours from 1 to 72. Convert days to hours. Always use '12' when the user gives no timeframe."),
    maxExperienceYears: z
      .string()
      .max(8)
      .optional()
      .default("")
      .describe("Maximum stated minimum experience from 0 to 20, or an empty string when the user did not set a limit."),
    optEligibleOnly: z
      .enum(["true", "false", ""])
      .optional()
      .default("false")
      .describe("Use 'true' only when the user asks for OPT-friendly or sponsorship-compatible roles. Otherwise use 'false'."),
    limit: z
      .string()
      .max(2)
      .optional()
      .default("5")
      .describe("Number of jobs to return, written as a string from '1' to '10'."),
  }),
  execute: async ({
    keywords,
    location,
    postedWithinHours,
    maxExperienceYears,
    optEligibleOnly,
    limit,
  }) => {
    const parsedHours = Number.parseInt(postedWithinHours, 10)
    const requestedHours = Number.isFinite(parsedHours)
      ? Math.max(1, Math.min(MAX_SEARCH_HOURS, parsedHours))
      : DEFAULT_SEARCH_HOURS
    const parsedExperience = Number.parseInt(maxExperienceYears, 10)
    const experienceLimit = Number.isFinite(parsedExperience)
      ? Math.max(0, Math.min(20, parsedExperience))
      : null
    const parsedLimit = Number.parseInt(limit, 10)
    const resultLimit = Number.isFinite(parsedLimit)
      ? Math.max(1, Math.min(10, parsedLimit))
      : 5
    const requireOptEligibility = optEligibleOnly === "true"
    const jobsInWindow = await currentJobs(requestedHours)
    const keywordTerms = normalizedTerms(keywords)
    const locationTerms = normalizedTerms(location)

    const ranked = jobsInWindow
      .map((job) => {
        const title = job.title.toLowerCase()
        const company = job.company.toLowerCase()
        const skills = [
          ...job.analysis.key_tech_skills,
          ...job.analysis.ats_keywords,
        ]
          .join(" ")
          .toLowerCase()
        const searchText = jobSearchText(job)
        const matchingKeywordTerms = keywordTerms.filter((term) => searchText.includes(term))
        const score = matchingKeywordTerms.reduce((total, term) => (
          total
          + (title.includes(term) ? 7 : 0)
          + (skills.includes(term) ? 4 : 0)
          + (company.includes(term) ? 2 : 0)
          + (searchText.includes(term) ? 1 : 0)
        ), 0)

        return { job, matchingKeywordTerms, score }
      })
      .filter(({ job, matchingKeywordTerms }) => {
        const minimumYears = job.analysis.minimum_years
        const locationText = job.location.toLowerCase()
        const requiredKeywordMatches = keywordTerms.length <= 2
          ? keywordTerms.length
          : Math.ceil(keywordTerms.length * 0.6)

        return (
          matchingKeywordTerms.length >= requiredKeywordMatches
          && (
            locationTerms.length === 0
            || locationTerms.some((term) => locationText.includes(term))
          )
          && (
            experienceLimit === null
            || (
              typeof minimumYears === "number"
              && minimumYears <= experienceLimit
            )
          )
          && (!requireOptEligibility || job.analysis.opt_eligible === "YES")
        )
      })
      .sort((first, second) => (
        second.score - first.score
        || (Date.parse(second.job.first_published_at) || 0)
          - (Date.parse(first.job.first_published_at) || 0)
      ))

    return {
      searchedJobs: jobsInWindow.length,
      totalMatches: ranked.length,
      returned: Math.min(resultLimit, ranked.length),
      criteria: {
        keywords: keywordTerms,
        location: location || "Any location",
        maxExperienceYears: experienceLimit,
        optEligibleOnly: requireOptEligibility,
        postedWithinHours: requestedHours,
      },
      jobs: ranked
        .slice(0, resultLimit)
        .map(({ job, matchingKeywordTerms }) => compactJob(job, matchingKeywordTerms)),
    }
  },
})

export function createJobAgent() {
  const model = getOpenRouterProvider().chat(
    process.env.OPENROUTER_MODEL ?? DEFAULT_OPENROUTER_MODEL,
    { parallelToolCalls: false },
  )

  return new ToolLoopAgent({
    id: "atsift-job-scout",
    model,
    instructions: `You are ATSift Job Scout, a read-only job-search agent.

Your process:
1. Understand the user's desired role, skills, location, experience limit, and OPT constraint.
2. Infer the requested posting timeframe. Convert days to hours. If the user gives no timeframe at all, postedWithinHours MUST be "12". The maximum available window is 72 hours.
3. Make one strong search plan. Put role titles and skills in keywords, geography in location, and only set experience or OPT constraints when the user asks for them.
4. Call searchJobs. The interface renders its verified results directly, so do not invent, list, or describe individual listings yourself.
5. After the tool result comes back, reply with exactly one short sentence acknowledging the result (for example "Found a few matches below." or "No matches for that this time - try widening the timeframe."). Never repeat, summarize, or add to the listings themselves.

The index contains all available jobs from the connected scanner, or the deployed snapshot when no scanner is connected. searchJobs is the only allowed source of job facts and URLs.`,
    tools: { searchJobs },
    temperature: 0.1,
    stopWhen: stepCountIs(2),
    prepareStep: ({ stepNumber }) => (
      stepNumber === 0
        ? {
            activeTools: ["searchJobs"],
            toolChoice: { type: "tool", toolName: "searchJobs" },
          }
        : undefined
    ),
  })
}
