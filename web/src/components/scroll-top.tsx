"use client"

import { useEffect, useState } from "react"
import { ArrowUp } from "lucide-react"

import { cn } from "@/lib/utils"

/*
  Back to the top of a long results list.

  Centred rather than tucked in a corner: the Job Scout already owns the
  bottom-right, and two round buttons stacked in the same corner would be a
  guess every time. It also sits at z-40, one layer under the Scout, so an
  open chat covers it instead of the two fighting.

  Hidden until you are a screen deep — before that the header is still within
  reach and the button would just be in the way.
*/

const REVEAL_AFTER_PX = 700

export function ScrollTop() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    let frame = 0

    function onScroll() {
      // Scroll fires far faster than the screen repaints; coalesce to one
      // read per frame so this never becomes the reason scrolling stutters.
      if (frame) return

      frame = requestAnimationFrame(() => {
        setVisible(window.scrollY > REVEAL_AFTER_PX)
        frame = 0
      })
    }

    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })

    return () => {
      window.removeEventListener("scroll", onScroll)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [])

  return (
    <button
      type="button"
      onClick={() => {
        // Honour the same preference the stylesheet does; a long smooth
        // scroll is exactly the kind of motion people turn this off for.
        const reduced = window.matchMedia(
          "(prefers-reduced-motion: reduce)",
        ).matches

        window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" })
      }}
      aria-label="Back to top"
      // Out of the tab order while hidden, so it is not a stop on an
      // invisible control.
      tabIndex={visible ? 0 : -1}
      aria-hidden={!visible}
      className={cn(
        // bottom-6 with a 48px circle puts its centre on the same line as the
        // Scout's 56px circle at bottom-5 — they read as one row of controls.
        "fixed bottom-6 left-1/2 z-40 -translate-x-1/2",
        "grid size-12 place-items-center rounded-full border border-line",
        "bg-surface/90 text-muted shadow-[0_4px_16px_rgba(8,12,20,0.12)]",
        "backdrop-blur transition-all duration-200",
        "hover:border-brand-line hover:bg-surface hover:text-brand-deep",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        visible
          ? "translate-y-0 opacity-100"
          : "pointer-events-none translate-y-3 opacity-0",
      )}
    >
      <ArrowUp aria-hidden="true" className="size-5" />
    </button>
  )
}
