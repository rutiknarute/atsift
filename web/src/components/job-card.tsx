"use client"

import { useId, useState } from "react"
import {
  ArrowUpRight,
  Building2,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  MapPin,
} from "lucide-react"

import { AtsBadge, LogoTile } from "@/components/brand"
import { detectBlocker } from "@/lib/eligibility"
import { experienceLabel } from "@/lib/experience"
import { cn, formatAge, formatStamp } from "@/lib/utils"
import type { Job } from "@/lib/types"

type Panel = "qa" | "summary" | null

interface JobCardProps {
  job: Job
  lastSeen: string | null
  onApply: (uid: string) => void
}

export function JobCard({ job, lastSeen, onApply }: JobCardProps) {
  const [panel, setPanel] = useState<Panel>(null)
  const panelId = useId()

  const analysis = job.analysis
  // `viewed` is what the scanner persists; opening the posting from the apply
  // button is the only thing that sets it, so it reads as "applied" here.
  const applied = Boolean(job.viewed)
  const detailsAvailable = Boolean(analysis)
  const blocked = analysis?.opt_eligible === "NO"
  // Read from the posting's own wording, not from the model's verdict.
  const blocker = detectBlocker(job)

  function toggle(next: Exclude<Panel, null>) {
    setPanel((current) => (current === next ? null : next))
  }

  return (
    <article className="flex min-w-0 flex-col rounded-[var(--radius-card)] border border-line bg-surface p-4 shadow-[0_1px_2px_rgba(8,12,20,0.05)] transition-shadow hover:shadow-[0_2px_10px_rgba(8,12,20,0.09)] sm:p-5">
      <div className="flex items-start gap-3">
        <LogoTile
          key={`${job.logo_url ?? ""}|${job.logo_fallback_url ?? ""}`}
          sources={[job.logo_url, job.logo_fallback_url]}
          label={job.company}
          className="size-12"
          placeholder={
            <Building2 aria-hidden="true" className="size-4 text-faint" />
          }
        />

        <div className="min-w-0 flex-1">
          <h3 className="text-balance font-display text-lg font-bold leading-tight tracking-tight">
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-sm decoration-1 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
            >
              {job.title}
              <ArrowUpRight
                aria-hidden="true"
                className="ml-1 inline size-3.5 text-faint"
              />
            </a>
          </h3>
          <p className="mt-0.5 break-words text-sm font-semibold text-brand">
            {job.company}
          </p>
          <p className="mt-1 flex items-start gap-1.5 text-sm leading-snug text-faint">
            <MapPin aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
            <span className="break-words">{job.location || "Not listed"}</span>
          </p>
        </div>

        <AtsBadge ats={job.ats} logoUrl={job.ats_logo_url} />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        <Tile>
          <dt className="label">Experience</dt>
          <dd className="mt-2 break-words font-display text-base font-bold">
            {experienceLabel(analysis)}
          </dd>
        </Tile>

        <Tile>
          <dt className="label">First published</dt>
          <dd className="mt-2 font-display text-base font-bold">
            {formatAge(job.age_hours)}
          </dd>
          <dd className="mt-0.5 break-words font-mono text-[11px] leading-snug text-faint">
            {formatStamp(job.posted_at)}
          </dd>
        </Tile>

        <Tile className="col-span-2 sm:col-span-1">
          <dt className="label">Last checked</dt>
          <dd className="mt-2 font-display text-base font-bold">
            {lastSeen ? formatAge(hoursSince(lastSeen)) : "This sample"}
          </dd>
          <dd className="mt-0.5 break-words font-mono text-[11px] leading-snug text-faint">
            {lastSeen ? formatStamp(lastSeen) : "Packaged snapshot"}
          </dd>
        </Tile>
      </dl>

      {/*
        One verdict, or nothing. A blocker the posting states outright beats
        the model's own guess, so it also suppresses an "OPT: YES" the model
        would otherwise have shown.
      */}
      {blocker ? (
        <p className="mt-3.5 flex items-start gap-2 break-words rounded-lg border border-danger-line bg-danger-bg px-3 py-2 text-sm font-medium leading-snug text-danger">
          <CircleAlert
            aria-hidden="true"
            className="mt-0.5 size-4 shrink-0"
          />
          {blocker.message}
        </p>
      ) : (
        detailsAvailable &&
        analysis && (
          <div className="mt-3.5 flex flex-wrap gap-2">
            {blocked ? (
              <Pill
                tone="danger"
                icon={<CircleAlert aria-hidden="true" className="size-3.5" />}
              >
                OPT: NO
              </Pill>
            ) : analysis.opt_eligible === "YES" ? (
              <Pill
                tone="brand"
                icon={<CheckCircle2 aria-hidden="true" className="size-3.5" />}
              >
                OPT: YES
              </Pill>
            ) : null}
          </div>
        )
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 pt-1">
        {detailsAvailable && (
          <div className="flex gap-2">
            <Toggle
              active={panel === "qa"}
              controls={`${panelId}-qa`}
              onClick={() => toggle("qa")}
            >
              Q&amp;A
            </Toggle>
            <Toggle
              active={panel === "summary"}
              controls={`${panelId}-summary`}
              onClick={() => toggle("summary")}
            >
              Summary
            </Toggle>
          </div>
        )}

        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => onApply(job.uid)}
          className={cn(
            "inline-flex min-h-11 items-center gap-1.5 rounded-xl px-5 text-sm font-semibold transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
            applied
              ? "border border-brand-line bg-brand-soft text-brand-deep hover:bg-brand-soft/70"
              : "bg-brand text-brand-ink hover:bg-brand-strong",
          )}
        >
          {applied ? (
            <>
              <CheckCircle2 aria-hidden="true" className="size-4" />
              Already Applied
            </>
          ) : (
            <>
              Apply now
              <ArrowUpRight aria-hidden="true" className="size-3.5" />
            </>
          )}
        </a>
      </div>

      {detailsAvailable && analysis && panel === "qa" && (
        <div
          id={`${panelId}-qa`}
          className="rise mt-4 border-t border-line-soft pt-4"
        >
          <div className="grid gap-5 sm:grid-cols-[1fr_10rem]">
            <dl className="space-y-2.5">
              <Row label="Degree" value={analysis.degree} />
              <Row label="Qualifications" value={analysis.qualifications} />
              <Row label="Eligibility" value={analysis.eligibility} />
              <Row
                label="Experience"
                value={experienceLabel(analysis)}
              />
            </dl>

            <dl>
              <dt className="label">Salary</dt>
              <dd className="mt-1 break-words text-sm text-muted">
                {analysis.salary || "Not listed."}
              </dd>
              <dt className="label mt-3">Team</dt>
              <dd className="mt-1 break-words text-sm text-muted">
                {analysis.team || "Not listed."}
              </dd>
            </dl>
          </div>

          {(analysis.key_tech_skills ?? []).length > 0 && (
            <ChipRow
              label="Key tech and skills"
              items={analysis.key_tech_skills}
            />
          )}

          {(analysis.ats_keywords ?? []).length > 0 && (
            <ChipRow
              label="Top ATS keywords"
              items={analysis.ats_keywords}
              outline
            />
          )}

          {analysis.tip && (
            <p className="mt-4 break-words rounded-lg border border-line bg-surface-2 px-4 py-3 text-sm leading-relaxed text-muted">
              <span className="font-semibold text-text">Tip: </span>
              {analysis.tip}
            </p>
          )}
        </div>
      )}

      {detailsAvailable && analysis && panel === "summary" && (
        <div
          id={`${panelId}-summary`}
          className="rise mt-4 border-t border-line-soft pt-4"
        >
          <dl className="grid gap-x-8 gap-y-2.5 sm:grid-cols-2">
            <SummaryRow label="Job ID" value={job.job_id} />
            <SummaryRow
              label="Team"
              value={job.team || analysis.team}
            />
            <SummaryRow label="Title" value={job.title} />
            <SummaryRow label="Company" value={job.company} />
            <SummaryRow label="Location" value={job.location} />
            <SummaryRow label="Source" value={job.ats} />
          </dl>

          {(job.category_labels ?? []).length > 0 && (
            <div className="mt-3.5 flex flex-wrap gap-1.5">
              {job.category_labels.map((label) => (
                <span
                  key={label}
                  className="rounded-md border border-line bg-surface-2 px-2 py-0.5 text-[11px] text-muted"
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

function hoursSince(stamp: string): number | null {
  const time = new Date(stamp).getTime()

  if (Number.isNaN(time)) return null

  return Math.max(0, (Date.now() - time) / 3_600_000)
}

function Tile({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-xl border border-line bg-surface px-3.5 py-3",
        className,
      )}
    >
      {children}
    </div>
  )
}

function Pill({
  tone,
  icon,
  children,
}: {
  tone: "brand" | "danger"
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold",
        tone === "brand" && "border-brand-line bg-brand-soft text-brand-deep",
        tone === "danger" && "border-danger-line bg-danger-bg text-danger",
      )}
    >
      {icon}
      {children}
    </span>
  )
}

function Toggle({
  active,
  controls,
  onClick,
  children,
}: {
  active: boolean
  controls: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={active}
      aria-controls={controls}
      className={cn(
        "inline-flex min-h-11 items-center gap-1.5 rounded-xl border px-4 text-sm font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        active
          ? "border-brand-line bg-brand-soft text-brand-deep"
          : "border-line bg-surface text-text hover:border-faint",
      )}
    >
      {children}
      <ChevronDown
        aria-hidden="true"
        className={cn(
          "size-3.5 transition-transform duration-200",
          active && "rotate-180",
        )}
      />
    </button>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  const displayValue = value?.trim() || "Not listed."

  return (
    <div className="break-words text-sm leading-relaxed">
      <dt className="inline text-faint">{label}: </dt>
      <dd className="inline text-text">{displayValue}</dd>
    </div>
  )
}

function SummaryRow({ label, value }: { label: string; value?: string }) {
  return (
    <div className="min-w-0 break-words text-sm leading-relaxed">
      <dt className="inline text-faint">{label}: </dt>
      <dd className="inline font-medium text-text">
        {value?.trim() || "Not listed."}
      </dd>
    </div>
  )
}

function ChipRow({
  label,
  items,
  outline = false,
}: {
  label: string
  items: string[]
  outline?: boolean
}) {
  return (
    <div className="mt-4">
      <span className="label">{label}</span>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {items.map((item) => (
          <span
            key={item}
            className={cn(
              "max-w-full break-words rounded-md px-2 py-1 text-[11px]",
              outline
                ? "border border-line text-muted"
                : "bg-surface-2 text-muted",
            )}
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  )
}
