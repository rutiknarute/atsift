import "server-only"

import type { Job } from "@/lib/types"

/*
  Each public job board has a stable marketing domain, which is all Logo.dev
  needs to serve the brand mark.
*/
const ATS_DOMAINS: Record<string, string> = {
  greenhouse: "greenhouse.io",
  ashby: "ashbyhq.com",
  lever: "lever.co",
  smartrecruiters: "smartrecruiters.com",
  workable: "workable.com",
  workday: "workday.com",
}

function logoDevUrl(identifier: string, size: number): string | null {
  const token = process.env.LOGO_DEV_PUBLISHABLE_KEY?.trim()

  if (!token) return null

  return (
    `https://img.logo.dev/${identifier}` +
    `?token=${encodeURIComponent(token)}` +
    `&size=${size}&retina=true&format=webp&fallback=404`
  )
}

function atsLogoUrl(ats: string): string | null {
  const domain = ATS_DOMAINS[(ats || "").trim().toLowerCase()]

  return domain ? logoDevUrl(domain, 48) : null
}

function companyLogoUrl(company: string): string | null {
  const name = (company || "").trim()

  return name ? logoDevUrl(`name/${encodeURIComponent(name)}`, 64) : null
}

/*
  The scanner resolves company artwork while it runs; this fills the gap for the
  packaged snapshot and for any company it could not resolve. The board logo is
  always derived here — it depends only on which ATS served the posting, so
  there is nothing for a scan to resolve.
*/
export function withLogos(job: Job): Job {
  return {
    ...job,
    logo_url: job.logo_url || companyLogoUrl(job.company),
    logo_fallback_url: job.logo_url ? job.logo_fallback_url : null,
    ats_logo_url: atsLogoUrl(job.ats),
  }
}
