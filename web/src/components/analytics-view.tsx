"use client"

import { useEffect, useMemo, useState } from "react"

const HISTORY_KEY = "atsift.application-history"

type ApplicationEvent = {
  uid: string
  appliedAt: string
  title?: string
  company?: string
  categories?: string[]
}

const ROLE_LABELS: Record<string, string> = {
  software: "Software",
  ai_ml: "AI / ML",
  data_engineer: "Data Engineer",
  data_analyst: "Data Analyst",
  new_grad: "New Grad",
  gtm: "GTM",
}

function dayKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}

function readHistory(): ApplicationEvent[] {
  try {
    const data: unknown = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]")
    if (!Array.isArray(data)) return []
    return data.filter((event): event is ApplicationEvent => event && typeof event.uid === "string" &&
      typeof event.appliedAt === "string" && Number.isFinite(Date.parse(event.appliedAt)) &&
      (event.title === undefined || typeof event.title === "string") &&
      (event.company === undefined || typeof event.company === "string") &&
      (event.categories === undefined || (Array.isArray(event.categories) && event.categories.every((category: unknown) => typeof category === "string"))))
  } catch { return [] }
}

function formatDay(value: string) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(
    new Date(`${value}T12:00:00`),
  )
}

export function recordApplication(
  uid: string,
  metadata?: { title?: string; company?: string; categories?: string[] },
) {
  try {
    const current = readHistory()
    if (current.some((event) => event.uid === uid)) return
    localStorage.setItem(HISTORY_KEY, JSON.stringify([
      ...current,
      { uid, appliedAt: new Date().toISOString(), ...metadata },
    ]))
    window.dispatchEvent(new Event("atsift:applications"))
  } catch {
    // Local analytics should never interfere with applying to a job.
  }
}

export function AnalyticsView() {
  const [events, setEvents] = useState<ApplicationEvent[]>([])
  const [selectedDay, setSelectedDay] = useState(dayKey(new Date()))
  const [today] = useState(() => new Date())

  useEffect(() => {
    const update = () => setEvents(readHistory())
    const timer = window.setTimeout(() => {
      update()
    }, 0)
    window.addEventListener("storage", update)
    window.addEventListener("atsift:applications", update)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener("storage", update)
      window.removeEventListener("atsift:applications", update)
    }
  }, [])

  const counts = useMemo(() => events.reduce<Record<string, number>>((result, event) => {
    const key = dayKey(new Date(event.appliedAt))
    result[key] = (result[key] ?? 0) + 1
    return result
  }, {}), [events])

  const roleCounts = useMemo(() => events.reduce<Record<string, number>>((result, event) => {
    const categories = event.categories?.length ? event.categories : ["other"]
    for (const category of categories) result[category] = (result[category] ?? 0) + 1
    return result
  }, {}), [events])

  const thisWeek = events.filter((event) => today.getTime() - new Date(event.appliedAt).getTime() < 7 * 24 * 60 * 60 * 1000).length
  const weeklyGoal = 10
  const recentEvents = [...events].sort((a, b) => b.appliedAt.localeCompare(a.appliedAt)).slice(0, 8)

  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date()
    date.setDate(date.getDate() - (6 - index))
    return dayKey(date)
  })

  return (
    <section className="workspace-section">
      <p className="label text-brand">Application activity</p>
      <h1 className="workspace-heading mt-3">Track your momentum.</h1>
      <p className="mt-4 max-w-2xl text-base leading-relaxed text-muted sm:text-lg">
        Compare your Apply clicks by day and role. History is saved in this browser; clicks do not confirm a submitted application.
      </p>

      <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
        {days.map((day) => (
          <button
            key={day}
            type="button"
            aria-pressed={selectedDay === day}
            onClick={() => setSelectedDay(day)}
            className={`rounded-2xl border p-4 text-left transition-colors ${selectedDay === day ? "border-brand-line bg-brand-soft" : "border-line bg-surface hover:bg-surface-2"}`}
          >
            <span className="block text-xs font-medium text-muted">{formatDay(day)}</span>
            <span className="mt-2 block text-3xl font-extrabold text-brand">{counts[day] ?? 0}</span>
            <span className="text-xs text-faint">applications</span>
          </button>
        ))}
      </div>

      <div aria-live="polite" className="ui-panel mt-6 p-5 text-sm text-muted">
        <span className="font-semibold text-text">{counts[selectedDay] ?? 0}</span> applications on {formatDay(selectedDay)}.
        <span className="ml-1 text-faint">Dated tracking starts with new applications from this update.</span>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="ui-panel p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-display text-lg font-bold text-text">Role mix</h2>
            <span className="text-xs text-faint">All tracked applications</span>
          </div>
          <div className="mt-4 space-y-3">
            {Object.entries(roleCounts).sort(([, a], [, b]) => b - a).map(([role, count]) => (
              <div key={role}>
                <div className="flex justify-between text-sm"><span className="text-muted">{ROLE_LABELS[role] ?? "Other"}</span><span className="font-semibold text-text">{count}</span></div>
                <div className="mt-1.5 h-2 rounded-full bg-surface-2"><div className="h-2 rounded-full bg-brand" style={{ width: `${Math.max(8, (count / Math.max(...Object.values(roleCounts), 1)) * 100)}%` }} /></div>
              </div>
            ))}
            {Object.keys(roleCounts).length === 0 && <p className="text-sm text-muted">Your role mix will appear after your first application.</p>}
          </div>
        </div>

        <div className="ui-panel p-5">
          <div className="flex items-center justify-between gap-3"><h2 className="font-display text-lg font-bold text-text">Weekly pace</h2><span className="text-sm font-semibold text-brand">{thisWeek}/{weeklyGoal}</span></div>
          <p className="mt-2 text-sm text-muted">Applications in the last 7 days.</p>
          <progress aria-label="Weekly goal progress" max={weeklyGoal} value={Math.min(thisWeek, weeklyGoal)} className="mt-5 h-3 w-full accent-brand" />
        </div>
      </div>

      <div className="ui-panel mt-6 p-5">
        <h2 className="font-display text-lg font-bold text-text">Recent applications</h2>
        <div className="mt-3 divide-y divide-line-soft">
          {recentEvents.map((event) => <div key={`${event.uid}-${event.appliedAt}`} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"><div><p className="font-semibold text-text">{event.title ?? "Tracked application"}</p><p className="text-muted">{event.company ?? "Company not recorded"}</p></div><span className="text-faint">{formatDay(dayKey(new Date(event.appliedAt)))}</span></div>)}
          {recentEvents.length === 0 && <p className="py-3 text-sm text-muted">No applications tracked yet.</p>}
        </div>
      </div>
    </section>
  )
}
