"use client"

import { useState } from "react"
import { useChat } from "@ai-sdk/react"
import { DefaultChatTransport } from "ai"
import { Bot, Loader2, Send, Sparkles } from "lucide-react"

import { cn } from "@/lib/utils"

const PROMPTS = [
  "Entry-level React roles from the last day",
  "Data analyst jobs that don't block OPT",
  "AI/ML roles needing under 2 years",
]

export function JobScout() {
  const [input, setInput] = useState("")

  const { messages, sendMessage, status, error } = useChat({
    transport: new DefaultChatTransport({ api: "/api/chat" }),
  })

  const busy = status === "streaming" || status === "submitted"

  function submit(text: string) {
    const trimmed = text.trim()

    if (!trimmed || busy) return

    void sendMessage({ text: trimmed })
    setInput("")
  }

  return (
    <section className="rounded-[var(--radius-card)] border border-line bg-surface/60 backdrop-blur-xl">
      <header className="flex items-center gap-2.5 border-b border-line-soft px-5 py-4">
        <Sparkles className="size-4 text-accent" />
        <h2 className="text-sm font-medium">AI Job Scout</h2>
        <span className="ml-auto text-[11px] text-faint">
          Searches scanned jobs in plain English
        </span>
      </header>

      <div className="max-h-96 overflow-y-auto px-5 py-4">
        {messages.length === 0 ? (
          <div className="py-4">
            <p className="text-sm text-faint">
              Ask for what you actually want.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => submit(prompt)}
                  className="rounded-full border border-line-soft bg-surface-2/50 px-3 py-1.5 text-xs text-muted transition-colors hover:border-accent hover:text-accent"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <ol className="flex flex-col gap-4">
            {messages.map((message) => (
              <li
                key={message.id}
                className={cn(
                  "flex gap-2.5 text-sm leading-relaxed",
                  message.role === "user" && "justify-end",
                )}
              >
                {message.role === "assistant" && (
                  <Bot className="mt-0.5 size-4 shrink-0 text-accent" />
                )}

                <div
                  className={cn(
                    "max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2",
                    message.role === "user"
                      ? "bg-accent text-accent-ink"
                      : "bg-surface-2 text-muted",
                  )}
                >
                  {message.parts
                    .filter((part) => part.type === "text")
                    .map((part, index) => (
                      <span key={index}>{part.text}</span>
                    ))}
                </div>
              </li>
            ))}

            {busy && (
              <li className="flex items-center gap-2 text-xs text-faint">
                <Loader2 className="size-3.5 animate-spin" />
                Searching scanned jobs…
              </li>
            )}
          </ol>
        )}

        {error && (
          <p className="mt-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error.message}
          </p>
        )}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          submit(input)
        }}
        className="flex items-center gap-2 border-t border-line-soft p-3"
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask the scout…"
          aria-label="Ask the Job Scout"
          className="flex-1 rounded-lg border border-line-soft bg-surface-2/50 px-3 py-2 text-sm placeholder:text-faint focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          aria-label="Send"
          className="rounded-lg bg-accent p-2 text-accent-ink transition-opacity hover:brightness-110 disabled:opacity-40"
        >
          <Send className="size-4" />
        </button>
      </form>
    </section>
  )
}
