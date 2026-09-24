"use client"

import { useEffect, useRef, type ReactNode } from "react"

export function JobDialog({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current!
    const previous = document.activeElement as HTMLElement | null
    const overflow = document.body.style.overflow
    dialog.showModal()
    document.body.style.overflow = "hidden"
    return () => {
      dialog.close()
      document.body.style.overflow = overflow
      previous?.focus()
    }
  }, [])
  return <dialog ref={ref} aria-labelledby="for-me-detail-title" onCancel={onClose}
    onClick={(event) => { if (event.target === event.currentTarget) onClose() }}
    className="job-dialog m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto overscroll-contain rounded-2xl border border-line bg-surface p-0 text-text shadow-2xl">
    {children}
  </dialog>
}
