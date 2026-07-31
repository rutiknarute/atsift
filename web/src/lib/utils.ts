import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatAge(hours: number | null): string {
  if (hours === null || Number.isNaN(hours)) return "—"

  if (hours < 1) {
    const minutes = Math.max(1, Math.round(hours * 60))
    return `${minutes}m ago`
  }

  if (hours < 24) return `${Math.round(hours)}h ago`

  const days = Math.round(hours / 24)

  return days === 1 ? "1 day ago" : `${days} days ago`
}

export function formatStamp(value: string | null): string {
  if (!value) return "—"

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) return "—"

  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

export function formatWindow(hours: number): string {
  if (hours < 24) return `${hours} hours`
  if (hours === 24) return "24 hours"

  return `${Math.round(hours / 24)} days`
}

export function pct(done: number, total: number): number {
  if (!total) return 0

  return Math.min(100, Math.round((done / total) * 100))
}
