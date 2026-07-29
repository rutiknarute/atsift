"use client"

import { useState } from "react"
import {
  ArrowUpRight,
  Building2,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  MapPin,
  TriangleAlert,
} from "lucide-react"

import { cleanExperience, cn, formatAge, formatStamp } from "@/lib/utils"
import type { Job } from "@/lib/types"

const ATS_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  ashby: "Ashby",
  lever: "Lever",
  smartrecruiters: "SmartRecruiters",
  workable: "Workable",
  workday: "Workday",
}

type Panel = "qa" | "summary" | null

interface JobCardProps {
  job: Job
  lastSeen: string | null
  onView: (uid: string) => void
}

export function JobCard({ job, lastSeen, onView }: JobCardProps) {
  const [panel, setPanel] = useState<Panel>(null)

  const analysis = job.analysis
  const blocked = analysis?.opt_eligible === "NO"
  const stale = job.age_hours !== null && job.age_hours > 120

  function toggle(next: Exclude<Panel, null>) {
    setPanel((current) => (current === next ? null : next))
  }

  return (
    <article
      className={cn(
        "rounded-[var(--radius-card)] border bg-surface/60 backdrop-blur-sm transition-colors",
        job.viewed ? "border-line-soft/60" : "border-line-soft",
        "hover:border-faint",
      )}
    >
      <div className="p-5">
        {/* Title block */}
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-line-soft bg-surface-2 text-faint">
            <Building2 className="size-4" />
          </span>

          <div className="min-w-0 flex-1">
            <h3 className="text-balance text-base font-semibold leading-snug">
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => onView(job.uid)}
                className="transition-colors hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                {job.title}
                <ArrowUpRight className="ml-1 inline size-3.5 opacity-50" />
              </a>
            </h3>

            <p className="mt-0.5 text-sm font-medium text-muted">
              {job.company}
            </p>

            <p className="mt-1 flex items-center gap-1.5 text-xs text-faint">
              <MapPin className="size-3" />
              {job.location || "Not listed"}
              <span className="text-line">·</span>
              {ATS_LABELS[job.ats] ?? job.ats}
            </p>
          </div>

          {job.viewed && (
            <span className="shrink-0 rounded-full border border-line-soft px-2 py-0.5 text-[10px] uppercase tracking-wide text-faint">
              Viewed
            </span>
          )}
        </div>

        {/* Stat tiles */}
        <dl className="mt-4 grid gap-2 sm:grid-cols-3">
          <Tile label="Experience">
            <div className="flex items-center justify-between gap-2">
              <span
                className={cn(
                  "text-sm font-semibold",
                  analysis?.minimum_years && analysis.minimum_years >= 4
                    ? "text-danger"
                    : "text-text",
                )}
              >
                {analysis?.minimum_years != null
                  ? `${analysis.minimum_years}+ years`
                  : cleanExperience(analysis?.experience_years)}
              </span>

              {analysis && <FitBadge analysis={analysis} />}
            </div>
          </Tile>

          <Tile label="First published">
            <span className="text-sm font-semibold">
              {formatAge(job.age_hours)}
            </span>
            <span className="mt-0.5 block text-[11px] text-faint">
              {formatStamp(job.posted_at)}
            </span>
          </Tile>

          <Tile label="Last seen">
            <span
              className={cn(
                "text-sm font-semibold",
                stale ? "text-warn" : "text-text",
              )}
            >
              {lastSeen ? formatStamp(lastSeen) : "This scan"}
            </span>
            {stale && (
              <span className="mt-0.5 block text-[11px] text-warn">
                may no longer be open
              </span>
            )}
          </Tile>
        </dl>

        {/* OPT verdict */}
        {analysis && (
          <div className="mt-3">
            {blocked ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-danger/30 bg-danger/10 px-3 py-1 text-xs font-medium text-danger">
                <TriangleAlert className="size-3.5" />
                OPT: NO
              </span>
            ) : analysis.opt_eligible === "YES" ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-xs font-medium text-accent">
                <CheckCircle2 className="size-3.5" />
                OPT: YES
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-line-soft px-3 py-1 text-xs text-faint">
                <CircleHelp className="size-3.5" />
                OPT: not screened
              </span>
            )}
          </div>
        )}

        {/* Panel toggles */}
        {analysis && (
          <div className="mt-4 flex flex-wrap gap-2">
            <PanelToggle
              active={panel === "qa"}
              onClick={() => toggle("qa")}
              label="Q&A"
            />
            <PanelToggle
              active={panel === "summary"}
              onClick={() => toggle("summary")}
              label="Summary"
            />
          </div>
        )}
      </div>

      {analysis && panel === "qa" && (
        <div className="rise border-t border-line-soft bg-surface-2/30 p-5">
          {blocked && analysis.opt_blocking_line && (
            <p className="mb-4 rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-xs leading-relaxed text-danger">
              <span className="font-medium">Blocking line: </span>
              {analysis.opt_blocking_line}
            </p>
          )}

          <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:gap-8">
            <dl className="space-y-2.5">
              <Row label="Degree" value={analysis.degree} />
              <Row label="Qualifications" value={analysis.qualifications} />
              <Row label="Eligibility" value={analysis.eligibility} />
              <Row
                label="Experience"
                value={cleanExperience(analysis.experience_years)}
              />
            </dl>

            <dl className="sm:w-44">
              <dt className="text-[11px] uppercase tracking-wide text-faint">
                Salary
              </dt>
              <dd className="mt-0.5 text-sm text-muted">{analysis.salary}</dd>

              <dt className="mt-3 text-[11px] uppercase tracking-wide text-faint">
                Team
              </dt>
              <dd className="mt-0.5 text-sm text-muted">{analysis.team}</dd>
            </dl>
          </div>

          {analysis.key_tech_skills.length > 0 && (
            <ChipRow label="Key tech and skills" items={analysis.key_tech_skills} />
          )}

          {analysis.ats_keywords.length > 0 && (
            <ChipRow label="Top ATS keywords" items={analysis.ats_keywords} muted />
          )}
        </div>
      )}

      {analysis && panel === "summary" && (
        <div className="rise border-t border-line-soft bg-surface-2/30 p-5">
          <p className="text-sm leading-relaxed text-muted">
            {analysis.qualifications}
          </p>

          {analysis.tip && analysis.tip !== "Analysis unavailable." && (
            <p className="mt-4 rounded-lg border border-info/25 bg-info/10 px-3 py-2 text-sm leading-relaxed">
              <span className="font-medium text-info">Tip: </span>
              {analysis.tip}
            </p>
          )}

          {job.category_labels.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
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
        </div>
      )}
    </article>
  )
}

function Tile({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-xl border border-line-soft bg-surface-2/40 px-3 py-2.5">
      <dt className="text-[10px] uppercase tracking-wide text-faint">
        {label}
      </dt>
      <dd className="mt-1">{children}</dd>
    </div>
  )
}

function FitBadge({ analysis }: { analysis: NonNullable<Job["analysis"]> }) {
  const years = analysis.minimum_years

  if (years == null) {
    return (
      <span className="rounded-full border border-line-soft px-2 py-0.5 text-[10px] uppercase tracking-wide text-faint">
        Fit: review
      </span>
    )
  }

  const good = years <= 2

  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide",
        good
          ? "border border-accent/30 bg-accent/10 text-accent"
          : "border border-warn/30 bg-warn/10 text-warn",
      )}
    >
      Fit: {good ? "good" : "review"}
    </span>
  )
}

function PanelToggle({
  active,
  onClick,
  label,
}: {
  active: boolean
  onClick: () => void
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        active
          ? "border-accent bg-accent/10 text-accent"
          : "border-line-soft bg-surface-2/50 text-muted hover:text-text",
      )}
    >
      {label}
      <ChevronDown
        className={cn("size-3 transition-transform", active && "rotate-180")}
      />
    </button>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap gap-x-2 text-sm leading-relaxed">
      <dt className="text-faint">{label}:</dt>
      <dd className="flex-1 text-muted">{value}</dd>
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
      <span className="text-[10px] uppercase tracking-wide text-faint">
        {label}
      </span>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {items.map((item) => (
          <span
            key={item}
            className={cn(
              "rounded-md px-2 py-1 text-[11px]",
              muted
                ? "border border-line-soft text-faint"
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
