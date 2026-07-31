export type CategoryId =
  | "software"
  | "new_grad"
  | "data_analyst"
  | "data_engineer"
  | "ai_ml"
  | "gtm"

export type Verdict = "YES" | "NO" | "UNKNOWN"

export interface JobAnalysis {
  us_location_eligible: Verdict
  opt_eligible: Verdict
  opt_blocking_line: string
  degree: string
  qualifications: string
  eligibility: string
  key_tech_skills: string[]
  experience_years: string
  minimum_years: number | null
  experience_fit?: string
  stop_after_experience?: boolean
  ats_keywords: string[]
  tip: string
  salary: string
  team: string
  analysis_failed?: boolean
}

export interface Job {
  uid: string
  ats: string
  company: string
  company_slug: string
  job_id: string
  title: string
  url: string
  location: string
  team: string
  posted_at: string | null
  age_hours: number | null
  description: string
  salary_context: string
  categories: CategoryId[]
  category_labels: string[]
  location_verdict?: "US" | "NON_US" | "AMBIGUOUS"
  analysis?: JobAnalysis
  viewed?: boolean
  logo_url?: string | null
  logo_fallback_url?: string | null
  ats_logo_url?: string | null
}

export interface ScanStatus {
  state: "idle" | "running" | "done" | "error"
  phase: string
  message: string
  companies_done: number
  companies_total: number
  jobs_found: number
  matches: number
  analyzed: number
  analyzed_total: number
  lookback_hours: number | null
  dataset: string | null
  started_at: string | null
  finished_at: string | null
  error: string | null
}

export interface JobsResponse {
  jobs: Job[]
  count: number
  scanned_at: string | null
  lookback_hours: number | null
  dataset: string | null
}

export interface ScannerMeta {
  categories: { id: CategoryId; label: string }[]
  datasets: { id: string; label: string; count: number }[]
  lookback_options: number[]
  default_lookback_hours: number
  max_lookback_hours: number
}

/*
  What the Job Scout's search tool returns per role.

  Lives here rather than in `job-agent.ts` because that module is server-only
  and the chat UI renders these as cards on the client. The tool builds the
  shape; both sides agree on it through this type.
*/
export interface ScoutJob {
  uid: string
  title: string
  company: string
  location: string
  ats: string
  ageHours: number | null
  minimumYears: number | null
  optEligible: "YES" | "NO" | "UNKNOWN"
  skills: string[]
  matchedTerms: string[]
  applyUrl: string
}

export interface ScoutSearchResult {
  source: "scanner" | "snapshot"
  searchedWithinHours: number | null
  totalInWindow: number
  matchCount: number
  jobs: ScoutJob[]
}
