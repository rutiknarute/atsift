"use client"

import { useMemo, useState } from "react"
import { MapPin, Sparkles, X } from "lucide-react"
import { ApplyButton } from "@/components/ui/apply-button"
import { JobDialog } from "@/components/ui/job-dialog"

import { LogoTile } from "@/components/brand"
import { formatAge, formatStamp } from "@/lib/utils"
import type { Job } from "@/lib/types"

export function ForMeView({ jobs, onApply, loading = false, source }: { jobs: Job[]; onApply: (uid: string) => void; loading?: boolean; source: "scanner" | "snapshot" }) {
  const [selectedUid, setSelectedUid] = useState<string | null>(null)
  const selectedJob = jobs.find((job) => job.uid === selectedUid)
  const recommendations = useMemo(() => {
    const preferenceScores = new Map<string, number>()

    for (const job of jobs) {
      if (!job.viewed) continue
      for (const category of job.categories ?? []) {
        preferenceScores.set(category, (preferenceScores.get(category) ?? 0) + 1)
      }
    }

    return jobs
      .filter((job) => (job.categories ?? []).includes("software"))
      .sort((a, b) => {
        const preferenceA = Math.max(...(a.categories ?? []).map((category) => preferenceScores.get(category) ?? 0), 0)
        const preferenceB = Math.max(...(b.categories ?? []).map((category) => preferenceScores.get(category) ?? 0), 0)
        return preferenceB - preferenceA || (a.age_hours ?? Infinity) - (b.age_hours ?? Infinity)
      })
      .slice(0, 30)
  }, [jobs])

  return (
    <section className="workspace-section">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles aria-hidden="true" className="size-5 text-brand" />
            <h1 className="workspace-heading">For me</h1>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-muted">Software roles ranked by your applied-job categories and posting date.</p>
        </div>
        <div className="flex items-center gap-2 text-xs font-medium text-faint">
          From your latest loaded scan
        </div>
      </div>

      {source === "snapshot" && <p className="mt-5 rounded-xl border border-line bg-surface-2 p-4 text-sm text-muted">Showing historical sample postings. Connect the scanner and run a scan for current roles.</p>}
      <div aria-busy={loading} className="ui-panel mt-7 overflow-hidden">
        <div className="flex items-center justify-between border-b border-line-soft px-4 py-4 sm:px-5">
          <h2 className="font-display text-lg font-bold">{source === "snapshot" ? "Sample roles" : "Fresh roles"}</h2>
          <span className="text-sm text-muted">{recommendations.length} of 30 recommendations</span>
        </div>

        {recommendations.length === 0 ? (
          <p role="status" className="px-5 py-12 text-center text-sm text-muted">{loading ? "Loading recommendations…" : "No software roles in these results. Run a scan to find more roles."}</p>
        ) : (
          <div className="divide-y divide-line-soft">
            {recommendations.map((job) => (
              <div
                key={job.uid}
                className="flex flex-wrap items-center gap-3 p-4 transition-colors hover:bg-brand-soft/45 sm:flex-nowrap sm:px-5"
              >
                <button type="button" onClick={() => setSelectedUid(job.uid)} aria-label={`View details for ${job.title} at ${job.company}`} className="grid min-w-0 flex-1 basis-full gap-3 rounded-xl text-left sm:basis-auto xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_auto] xl:items-center">
                <div className="flex min-w-0 items-center gap-3">
                  <LogoTile
                    sources={[job.logo_url, job.logo_fallback_url]}
                    label={job.company}
                    className="size-10 rounded-xl"
                    placeholder={<Sparkles aria-hidden="true" className="size-4 text-brand" />}
                  />
                  <div className="min-w-0">
                    <span className="block text-sm font-bold leading-snug text-text">{job.title}</span>
                    <p className="truncate text-sm text-muted">{job.company}</p>
                  </div>
                </div>
                <p className="flex min-w-0 items-center gap-1.5 truncate text-sm text-muted">
                  <MapPin aria-hidden="true" className="size-3.5 shrink-0 text-faint" />
                  <span className="truncate">{job.location || "Location not listed"}</span>
                </p>
                <span className="text-sm text-muted">{formatAge(job.age_hours)}</span>
                </button>
                <div className="flex items-center gap-2 justify-self-start sm:justify-self-end">
                  <ApplyButton uid={job.uid} url={job.url} applied={job.viewed} onApply={onApply} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {selectedJob && (
        <JobDialog onClose={() => setSelectedUid(null)}>
          <article
            className="p-5 sm:p-7"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <LogoTile
                  sources={[selectedJob.logo_url, selectedJob.logo_fallback_url]}
                  label={selectedJob.company}
                  className="size-12 rounded-xl"
                  placeholder={<Sparkles aria-hidden="true" className="size-5 text-brand" />}
                />
                <div className="min-w-0">
                  <h2 id="for-me-detail-title" className="text-balance font-display text-xl font-extrabold leading-tight">{selectedJob.title}</h2>
                  <p className="mt-1 text-sm font-semibold text-brand">{selectedJob.company}</p>
                </div>
              </div>
              <button type="button" aria-label="Close job details" onClick={() => setSelectedUid(null)} className="inline-flex size-11 shrink-0 items-center justify-center rounded-xl text-faint hover:bg-surface-2 hover:text-text">
                <X aria-hidden="true" className="size-5" />
              </button>
            </div>

            <dl className="mt-6 grid grid-cols-2 gap-3">
              <Detail label="Posted" value={formatStamp(selectedJob.posted_at)} />
              <Detail label="Location" value={selectedJob.location || "Not listed"} />
              <Detail label="Role" value={selectedJob.title} />
              <Detail label="Source" value={selectedJob.ats} />
              <Detail label="Team" value={selectedJob.team || "Not listed"} />
              <Detail label="Experience" value={selectedJob.analysis?.experience_years || "Not listed"} />
            </dl>

            {selectedJob.analysis && (
              <div className="mt-6 space-y-4 border-t border-line-soft pt-5">
                <h3 className="font-display text-base font-bold">Screening answers</h3>
                <dl className="grid gap-3 sm:grid-cols-2">
                  <Detail label="US location" value={selectedJob.analysis.us_location_eligible} />
                  <Detail label="OPT eligibility" value={selectedJob.analysis.opt_eligible} />
                  <Detail label="Degree" value={selectedJob.analysis.degree} />
                  <Detail label="Salary" value={selectedJob.analysis.salary || "Not listed"} />
                  <Detail label="Qualifications" value={selectedJob.analysis.qualifications} />
                  <Detail label="Eligibility" value={selectedJob.analysis.eligibility} />
                  <Detail label="Skills" value={selectedJob.analysis.key_tech_skills?.join(", ")} />
                  <Detail label="OPT blocker" value={selectedJob.analysis.opt_blocking_line || "None identified"} />
                </dl>
                {selectedJob.analysis.tip && <p className="rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm leading-relaxed text-muted"><span className="font-semibold text-text">Tip: </span>{selectedJob.analysis.tip}</p>}
              </div>
            )}

            <section className="mt-6 border-t border-line-soft pt-5">
              <h3 className="font-display text-lg font-bold">Job description</h3>
              <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-relaxed text-muted">{selectedJob.description || "No description available for this posting."}</p>
            </section>
            <div className="sticky -bottom-7 mt-6 flex flex-wrap justify-end gap-3 border-t border-line-soft bg-surface py-4">
              <button type="button" onClick={() => setSelectedUid(null)} className="min-h-11 rounded-xl px-4 text-sm font-semibold text-muted hover:bg-surface-2">Close</button>
              <ApplyButton uid={selectedJob.uid} url={selectedJob.url} applied={selectedJob.viewed} onApply={onApply} />
            </div>
          </article>
        </JobDialog>
      )}
    </section>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface-2 px-3 py-2.5">
      <dt className="label">{label}</dt>
      <dd className="mt-1 break-words text-sm font-medium text-text">{value || "Not listed"}</dd>
    </div>
  )
}
