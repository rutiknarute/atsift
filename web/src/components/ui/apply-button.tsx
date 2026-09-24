import { ArrowUpRight, CheckCircle2 } from "lucide-react"
import { cn } from "@/lib/utils"

export function ApplyButton({ uid, url, applied, onApply }: {
  uid: string
  url: string
  applied?: boolean
  onApply: (uid: string) => void
}) {
  return <a href={url} target="_blank" rel="noopener noreferrer"
    onClick={() => onApply(uid)}
    className={cn("inline-flex min-h-11 shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-xl px-4 text-sm font-semibold transition-colors", applied
      ? "border border-brand-line bg-brand-soft text-brand-deep hover:bg-brand-soft/70"
      : "bg-brand text-brand-ink hover:bg-brand-strong")}>
    {applied ? <CheckCircle2 aria-hidden="true" className="size-4" /> : <ArrowUpRight aria-hidden="true" className="size-4" />}
    {applied ? "Already Applied" : "Apply now"}
  </a>
}
