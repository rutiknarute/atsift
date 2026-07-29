"use client"

import { useState } from "react"
import {
  ArrowUpRight,
  BadgeCheck,
  ChevronDown,
  Clock,
  MapPin,
  TriangleAlert,
} from "lucide-react"

import { cn, formatAge } from "@/lib/utils"
import type { Job } from "@/lib/types"

const ATS_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  ashby: "Ashby",
  lever: "Lever",
  smartrecruiters: "SmartRecruiters",
  workable: "Workable",
  workday: "Workday",
}

interface JobCardProps {
  job: Job
  onView: (uid: string) => void
}

export function JobCard({ job, onView }: JobCardProps) {
  const [open, setOpen] = useState(false)
  const analysis = job.analysis
  const blocked = analysis?.opt_eligible === "NO"
  const fresh = job.age_hours !== null && job.age_hours <= 12

  return (
    <article
      className={cn(
        "group rounded-[var(--radius-card)] border bg-surface/60 backdrop-blur-sm transition-all duration-200",
        "hover:border-faint hover:bg-surface",
        job.viewed ? "border-line-soft/60 opacity-70" : "border-line-soft",
      )}
    >
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-muted">
                {job.company}
              </span>

              {fresh && (
                <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                  Fresh
                </span>
              )}

              {job.viewed && (
                <span className="text-[10px] uppercase tracking-wide text-faint">
                  Viewed
                </span>
              )}
            </div>

            <h3 className="mt-1 text-balance text-lg font-semibold leading-snug">
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => onView(job.uid)}
                className="transition-colors hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                {job.title}
                <ArrowUpRight className="ml-1 inline size-4 opacity-0 transition-opacity group-hover:opacity-60" />
              </a>
            </h3>
          </div>

          {blocked ? (
            <span
              title="This posting appears to block OPT candidates"
              className="flex shrink-0 items-center gap-1 rounded-full border border-danger/30 bg-danger/10 px-2.5 py-1 text-[11px] font-medium text-danger"
            >
              <TriangleAlert className="size-3" />
              OPT blocked
            </span>
          ) : analysis?.opt_eligible === "YES" ? (
            <span className="flex shrink-0 items-center gap-1 rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 text-[11px] font-medium text-accent">
              <BadgeCheck className="size-3" />
              OPT ok
            </span>
          ) : null}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-faint">
          <span className="flex items-center gap-1.5">
            <MapPin className="size-3" />
            {job.location || "Not listed"}
          </span>
          <span className="flex items-center gap-1.5">
            <Clock className="size-3" />
            {formatAge(job.age_hours)}
          </span>
          <span>{ATS_LABELS[job.ats] ?? job.ats}</span>
          {analysis?.salary && analysis.salary !== "Not listed." && (
            <span className="text-accent">{analysis.salary}</span>
          )}
        </div>

        {job.category_labels.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {job.category_labels.map((label) => (
              <span
                key={label}
                className="rounded-md bg-surface-2 px-2 py-0.5 text-[11px] text-muted"
              >
                {label}
              </span>
            ))}
          </div>
        )}

        {analysis && (
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="mt-4 flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <ChevronDown
              className={cn(
                "size-3.5 transition-transform duration-200",
                open && "rotate-180",
              )}
            />
            {open ? "Hide" : "Show"} AI breakdown
          </button>
        )}
      </div>

      {analysis && open && (
        <div className="rise border-t border-line-soft bg-surface-2/30 p-5">
          {blocked && analysis.opt_blocking_line && (
            <p className="mb-4 rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-xs leading-relaxed text-danger">
              <span className="font-medium">Blocking line: </span>
              {analysis.opt_blocking_line}
            </p>
          )}

          <dl className="grid gap-4 sm:grid-cols-2">
            <Field label="Degree" value={analysis.degree} />
            <Field label="Experience" value={analysis.experience_years} />
            <Field label="Qualifications" value={analysis.qualifications} />
            <Field label="Team" value={analysis.team} />
          </dl>

          {analysis.key_tech_skills.length > 0 && (
            <ChipRow label="Key skills" items={analysis.key_tech_skills} />
          )}

          {analysis.ats_keywords.length > 0 && (
            <ChipRow
              label="ATS résumé keywords"
              items={analysis.ats_keywords}
              muted
            />
          )}

          {analysis.tip && analysis.tip !== "Analysis unavailable." && (
            <p className="mt-4 rounded-lg border border-info/25 bg-info/10 px-3 py-2 text-xs leading-relaxed">
              <span className="font-medium text-info">Tip: </span>
              {analysis.tip}
            </p>
          )}
        </div>
      )}
    </article>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-faint">
        {label}
      </dt>
      <dd className="mt-0.5 text-sm leading-relaxed text-muted">{value}</dd>
    </div>
  )
}

function ChipRow({
  label,
  items,
  muted = false,
}: {
  label: string
  items: string[]
  muted?: boolean
}) {
  return (
    <div className="mt-4">
      <span className="text-[11px] uppercase tracking-wide text-faint">
        {label}
      </span>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {items.map((item) => (
          <span
            key={item}
            className={cn(
              "rounded-md px-2 py-0.5 text-[11px]",
              muted
                ? "bg-surface-2 text-faint"
                : "border border-accent/25 bg-accent/10 text-accent",
            )}
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  )
}
