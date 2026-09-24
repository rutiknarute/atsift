"use client"

import { useRef } from "react"

/*
  The word disappears the way the sentence says it does. Each letter is its own
  animated element so the fade can travel across the word instead of dropping
  it all at once — the sentence stays readable throughout, and assistive tech
  reads the plain word from the visually hidden copy.

  Shared by the dashboard hero and the login page: it is the one piece of the
  brand that moves, so both places have to move identically.
*/
export function VanishingWord({ word }: { word: string }) {
  const letters = useRef<Array<HTMLSpanElement | null>>([])

  function resetRepulsion() {
    letters.current.forEach((letter) => {
      if (letter) letter.style.transform = ""
    })
  }

  function repelFromPointer(event: React.PointerEvent<HTMLSpanElement>) {
    if (event.pointerType === "touch" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    const radius = 170

    letters.current.forEach((letter) => {
      if (!letter) return

      const bounds = letter.getBoundingClientRect()
      const centerX = bounds.left + bounds.width / 2
      const centerY = bounds.top + bounds.height / 2
      const distanceX = centerX - event.clientX
      const distanceY = centerY - event.clientY
      const distance = Math.hypot(distanceX, distanceY)

      if (distance >= radius || distance === 0) {
        letter.style.transform = ""
        return
      }

      const strength = (1 - distance / radius) ** 2
      const offset = Math.min(24, strength * 28)
      letter.style.transform = `translate(${(distanceX / distance) * offset}px, ${(distanceY / distance) * offset}px)`
    })
  }

  return (
    <span
      className="text-brand"
      onPointerMove={repelFromPointer}
      onPointerLeave={resetRepulsion}
    >
      <span className="sr-only">{word}</span>
      <span aria-hidden="true" className="vanish">
        {[...word].map((letter, index) => (
          <span
            key={index}
            ref={(element) => {
              letters.current[index] = element
            }}
            className="vanish-letter"
          >
            <span
              className="vanish-glyph"
              style={{ "--letter": index } as React.CSSProperties}
            >
              {letter}
            </span>
          </span>
        ))}
      </span>
    </span>
  )
}
