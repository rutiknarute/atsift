import { ArrowUpRight } from "lucide-react"

import { cn } from "@/lib/utils"

/*
  Just enough formatting for what the Scout actually writes: short lines,
  bullet lists, the occasional bold label, and an apply link per role. Those
  links are the point of the answer, so they have to be clickable — plain
  pre-wrapped text left them as dead strings the user had to copy out.

  Deliberately not a markdown library. The surface is this small, the input is
  one known model, and a parser we own cannot render anything we did not ask
  for.
*/

const INLINE =
  /(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<>()]+|\*\*[^*\n]+\*\*|`[^`\n]+`)/g

const BULLET = /^\s*[-*•]\s+/

function tidyUrl(url: string): { href: string; trailing: string } {
  // Sentence punctuation clings to the end of a bare URL.
  const match = url.match(/[).,;:!?]+$/)

  if (!match) return { href: url, trailing: "" }

  return {
    href: url.slice(0, -match[0].length),
    trailing: match[0],
  }
}

function shorten(href: string): string {
  try {
    const { hostname, pathname } = new URL(href)
    const host = hostname.replace(/^www\./, "")

    if (href.length <= 44) return host + (pathname === "/" ? "" : pathname)

    return host
  } catch {
    return href
  }
}

function Link({ href, children }: { href: string; children: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-baseline gap-0.5 break-all font-medium text-brand underline decoration-brand/30 underline-offset-2 transition-colors hover:decoration-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
    >
      {children}
      <ArrowUpRight aria-hidden="true" className="size-3 shrink-0" />
    </a>
  )
}

function inline(text: string, keyPrefix: string) {
  return text.split(INLINE).map((token, index) => {
    const key = `${keyPrefix}-${index}`

    if (!token) return null

    const labelled = token.match(/^\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)$/)

    if (labelled) {
      return (
        <Link key={key} href={labelled[2]}>
          {labelled[1]}
        </Link>
      )
    }

    if (/^https?:\/\//.test(token)) {
      const { href, trailing } = tidyUrl(token)

      return (
        <span key={key}>
          <Link href={href}>{shorten(href)}</Link>
          {trailing}
        </span>
      )
    }

    if (/^\*\*[^*\n]+\*\*$/.test(token)) {
      return (
        <strong key={key} className="font-semibold text-text">
          {token.slice(2, -2)}
        </strong>
      )
    }

    if (/^`[^`\n]+`$/.test(token)) {
      return (
        <code
          key={key}
          className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.85em]"
        >
          {token.slice(1, -1)}
        </code>
      )
    }

    return <span key={key}>{token}</span>
  })
}

export function RichText({
  children,
  className,
}: {
  children: string
  className?: string
}) {
  const lines = children.replace(/\r\n/g, "\n").split("\n")
  const blocks: React.ReactNode[] = []
  let bullets: string[] = []
  let paragraph: string[] = []

  function flushBullets() {
    if (bullets.length === 0) return

    const items = bullets
    bullets = []
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="space-y-1.5 pl-1">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2">
            <span
              aria-hidden="true"
              className="mt-[0.55em] size-1 shrink-0 rounded-full bg-brand"
            />
            <span className="min-w-0">
              {inline(item, `li-${blocks.length}-${index}`)}
            </span>
          </li>
        ))}
      </ul>,
    )
  }

  function flushParagraph() {
    if (paragraph.length === 0) return

    const text = paragraph.join("\n")
    paragraph = []
    blocks.push(
      <p key={`p-${blocks.length}`} className="whitespace-pre-wrap">
        {inline(text, `p-${blocks.length}`)}
      </p>,
    )
  }

  for (const line of lines) {
    if (BULLET.test(line)) {
      flushParagraph()
      bullets.push(line.replace(BULLET, ""))
      continue
    }

    flushBullets()

    if (line.trim() === "") {
      flushParagraph()
      continue
    }

    paragraph.push(line)
  }

  flushBullets()
  flushParagraph()

  return (
    <div className={cn("space-y-2.5 leading-relaxed", className)}>
      {blocks}
    </div>
  )
}
