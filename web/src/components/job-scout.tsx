"use client"

import { useEffect, useId, useRef, useState } from "react"
import { useChat } from "@ai-sdk/react"
import { DefaultChatTransport } from "ai"
import {
  ArrowUp,
  Clock,
  MapPin,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Square,
  X,
} from "lucide-react"

import { RichText } from "@/components/ui/rich-text"
import { cn } from "@/lib/utils"

const LIVE_PROMPTS = [
  {
    icon: Clock,
    text: "Entry-level React roles from the last day",
  },
  {
    icon: ShieldCheck,
    text: "Data analyst jobs that don't block OPT",
  },
  {
    icon: MapPin,
    text: "AI/ML roles needing under 2 years",
  },
]

const SAMPLE_PROMPTS = [
  { icon: Clock, text: "React roles in this sample" },
  { icon: ShieldCheck, text: "Data analyst roles marked OPT eligible" },
  { icon: MapPin, text: "AI/ML roles with listed experience" },
]

const transport = new DefaultChatTransport({ api: "/api/chat" })

export function JobScout({ sampleMode = false }: { sampleMode?: boolean }) {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState("")
  const panelId = useId()
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const launcherRef = useRef<HTMLButtonElement>(null)
  const feedRef = useRef<HTMLDivElement>(null)

  const { messages, sendMessage, status, error, setMessages, stop } = useChat({
    transport,
  })

  const busy = status === "streaming" || status === "submitted"
  const prompts = sampleMode ? SAMPLE_PROMPTS : LIVE_PROMPTS

  // Escape closes, and focus lands where the user expects on both edges.
  useEffect(() => {
    if (!open) {
      launcherRef.current?.focus({ preventScroll: true })

      return
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false)
    }

    window.addEventListener("keydown", onKeyDown)
    inputRef.current?.focus()

    return () => window.removeEventListener("keydown", onKeyDown)
  }, [open])

  // Follow the reply as it streams in.
  useEffect(() => {
    feedRef.current?.scrollTo({
      top: feedRef.current.scrollHeight,
      behavior: "smooth",
    })
  }, [messages, busy])

  // Grow the composer with its content, up to a point.
  useEffect(() => {
    const field = inputRef.current

    if (!field) return

    field.style.height = "auto"
    field.style.height = `${Math.min(field.scrollHeight, 132)}px`
  }, [input])

  function submit(text: string) {
    const trimmed = text.trim()

    if (!trimmed || busy) return

    void sendMessage({ text: trimmed })
    setInput("")
  }

  return (
    <>
      {/*
        Pinned to the viewport, so it rides along however far down the list you
        scroll and is always one click from bringing the Scout back up.
      */}
      <button
        ref={launcherRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label="Open AI Job Scout"
        className={cn(
          "fixed bottom-5 right-5 z-50 grid size-14 place-items-center rounded-full",
          "bg-brand text-brand-ink shadow-[0_8px_24px_rgba(0,90,253,0.32)]",
          "transition-all duration-200 hover:scale-105 hover:bg-brand-strong",
          "hover:shadow-[0_10px_28px_rgba(0,90,253,0.42)]",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
          open && "pointer-events-none scale-90 opacity-0",
        )}
      >
        <Sparkles aria-hidden="true" className="size-6" />
      </button>

      {open && (
        <div
          role="presentation"
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-50 bg-text/30 backdrop-blur-[3px] lg:bg-text/15"
        />
      )}

      <aside
        id={panelId}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${panelId}-heading`}
        aria-hidden={!open}
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-surface sm:max-w-[30rem] lg:max-w-[34rem]",
          "border-l border-line shadow-[-12px_0_40px_rgba(8,12,20,0.14)]",
          "transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center gap-3 border-b border-line px-4 py-3.5">
          <span
            aria-hidden="true"
            className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand text-brand-ink"
          >
            <Sparkles className="size-[1.1rem]" />
          </span>

          <div className="min-w-0 flex-1">
            <h2
              id={`${panelId}-heading`}
              className="font-display text-[0.95rem] font-bold leading-tight"
            >
              Job Scout
            </h2>
            <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-faint">
              <span
                aria-hidden="true"
                className={cn(
                  "size-1.5 rounded-full",
                  sampleMode ? "bg-faint" : "bg-brand",
                )}
              />
              {sampleMode ? "Searching the sample" : "Searching scanned roles"}
            </p>
          </div>

          {messages.length > 0 && (
            <button
              type="button"
              onClick={() => {
                stop()
                setMessages([])
                setInput("")
                inputRef.current?.focus()
              }}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-faint transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <RotateCcw aria-hidden="true" className="size-3.5" />
              New
            </button>
          )}

          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close Job Scout"
            className="grid size-9 shrink-0 place-items-center rounded-lg text-faint transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </header>

        <div
          ref={feedRef}
          className="flex-1 overflow-y-auto overscroll-contain px-4 py-5"
        >
          {messages.length === 0 ? (
            <div className="flex h-full flex-col justify-center py-6">
              <div className="text-center">
                <span
                  aria-hidden="true"
                  className="mx-auto grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand"
                >
                  <Sparkles className="size-6" />
                </span>
                <h3 className="mt-4 font-display text-lg font-bold tracking-tight">
                  Ask for the role you want
                </h3>
                <p className="mx-auto mt-1.5 max-w-[19rem] text-pretty text-sm leading-relaxed text-muted">
                  {sampleMode
                    ? "Plain English works. These results come from the packaged sample, not live listings."
                    : "Plain English works. Scout only answers from roles this scan actually found."}
                </p>
              </div>

              <div className="mt-6 flex flex-col gap-2">
                {prompts.map(({ icon: Icon, text }) => (
                  <button
                    key={text}
                    type="button"
                    onClick={() => submit(text)}
                    className="group flex min-h-12 items-center gap-3 rounded-xl border border-line bg-surface px-3.5 text-left text-[13px] font-medium leading-snug text-muted transition-all hover:-translate-y-px hover:border-brand-line hover:bg-brand-soft hover:text-brand-deep hover:shadow-[0_2px_8px_rgba(8,12,20,0.06)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
                  >
                    <Icon
                      aria-hidden="true"
                      className="size-4 shrink-0 text-faint transition-colors group-hover:text-brand"
                    />
                    {text}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <ol className="flex flex-col gap-5">
              {messages.map((message) => {
                const text = message.parts
                  .filter((part) => part.type === "text")
                  .map((part) => part.text)
                  .join("")

                if (message.role === "user") {
                  return (
                    <li key={message.id} className="rise flex justify-end">
                      <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand px-3.5 py-2.5 text-sm leading-relaxed text-brand-ink">
                        {text}
                      </p>
                    </li>
                  )
                }

                /*
                  No bubble on the answer. A reply is often several roles with
                  links — it reads as a document, and boxing it in wastes the
                  width the drawer exists to provide.
                */
                return (
                  <li key={message.id} className="rise flex gap-2.5">
                    <span
                      aria-hidden="true"
                      className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand"
                    >
                      <Sparkles className="size-3.5" />
                    </span>
                    <RichText className="min-w-0 flex-1 text-sm text-muted">
                      {text}
                    </RichText>
                  </li>
                )
              })}

              {busy && (
                <li className="flex items-center gap-2.5" aria-live="polite">
                  <span
                    aria-hidden="true"
                    className="grid size-6 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand"
                  >
                    <Sparkles className="size-3.5" />
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="typing" aria-hidden="true">
                      <span />
                      <span />
                      <span />
                    </span>
                    <span className="text-xs text-faint">
                      Searching roles…
                    </span>
                  </span>
                </li>
              )}
            </ol>
          )}

          {error && (
            <p
              role="alert"
              className="mt-4 rounded-xl border border-danger-line bg-danger-bg px-3.5 py-2.5 text-xs leading-relaxed text-danger"
            >
              Scout is unavailable. Check the AI configuration and try again.
            </p>
          )}
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault()
            submit(input)
          }}
          className="border-t border-line p-3"
        >
          <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface-2 p-2 transition-colors focus-within:border-brand focus-within:bg-surface focus-within:ring-2 focus-within:ring-brand/20">
            <textarea
              ref={inputRef}
              name="job-scout-query"
              rows={1}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault()
                  submit(input)
                }
              }}
              placeholder="Ask for a role, a stack, a timeframe…"
              aria-label="Ask the Job Scout"
              className="max-h-[8.25rem] min-h-9 flex-1 resize-none bg-transparent px-1.5 py-1.5 text-base leading-relaxed outline-none placeholder:text-faint sm:text-sm"
            />

            {busy ? (
              <button
                type="button"
                onClick={stop}
                aria-label="Stop generating"
                className="grid size-9 shrink-0 place-items-center rounded-xl border border-line bg-surface text-muted transition-colors hover:border-faint hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <Square aria-hidden="true" className="size-3 fill-current" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                aria-label="Send"
                className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand text-brand-ink transition-all hover:bg-brand-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-line disabled:text-faint"
              >
                <ArrowUp aria-hidden="true" className="size-4" />
              </button>
            )}
          </div>

          <p className="mt-2 px-1 text-center text-[11px] text-faint">
            <kbd className="font-mono">Enter</kbd> to send ·{" "}
            <kbd className="font-mono">Shift</kbd>+
            <kbd className="font-mono">Enter</kbd> for a new line
          </p>
        </form>
      </aside>
    </>
  )
}
