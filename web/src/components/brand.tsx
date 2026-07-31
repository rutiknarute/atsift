"use client"

import { useState } from "react"
import Image from "next/image"
import { Database } from "lucide-react"

import atsiftLogo from "@/assets/atsift-logo.png"
import { cn } from "@/lib/utils"

/*
  The wordmark is the supplied artwork, trimmed to its own edges — the source
  file carried 592px of empty padding on the left and none at the bottom,
  which would have hung the lockup off-centre in the header. No plate, no
  border, nothing drawn around it.
*/
export function BrandLogo({ className }: { className?: string }) {
  return (
    <Image
      src={atsiftLogo}
      alt="ATSift"
      sizes="180px"
      priority
      className={cn("h-7 w-auto sm:h-8", className)}
    />
  )
}

const ATS_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  ashby: "Ashby",
  lever: "Lever",
  smartrecruiters: "SmartRecruiters",
  workable: "Workable",
  workday: "Workday",
}

/*
  A rounded square the artwork fills edge to edge. No border: the tile is a
  shape for the logo to sit in, not a frame drawn around it. Sources are tried
  in order, so a dead CDN URL falls through to the next one and finally to the
  caller's placeholder.
*/
export function LogoTile({
  sources,
  label,
  placeholder,
  className,
}: {
  sources: (string | null | undefined)[]
  label: string
  placeholder: React.ReactNode
  className?: string
}) {
  const candidates = sources.filter((source): source is string =>
    Boolean(source),
  )
  const [index, setIndex] = useState(0)
  const source = candidates[index]

  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center overflow-hidden rounded-xl bg-surface-2",
        className,
      )}
      title={label}
    >
      {source ? (
        // Provider hosts are dynamic, so a native image keeps the fallback
        // chain reliable without broadening Next.js image host permissions.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={source}
          alt=""
          aria-hidden="true"
          loading="lazy"
          decoding="async"
          referrerPolicy="origin"
          onError={() => setIndex((current) => current + 1)}
          className="size-full object-contain"
        />
      ) : (
        placeholder
      )}
      <span className="sr-only">{label}</span>
    </span>
  )
}

export function AtsBadge({
  ats,
  logoUrl,
}: {
  ats: string
  logoUrl?: string | null
}) {
  const label = ATS_LABELS[ats] ?? (ats || "Unknown ATS")

  return (
    <LogoTile
      key={logoUrl ?? ""}
      sources={[logoUrl]}
      label={`Source: ${label}`}
      className="size-9"
      placeholder={<Database aria-hidden="true" className="size-4 text-faint" />}
    />
  )
}
