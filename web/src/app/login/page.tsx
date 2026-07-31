"use client"

import { Suspense, useEffect, useRef, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  MapPin,
  PlayCircle,
  Send,
  ShieldCheck,
  Timer,
  UserRound,
} from "lucide-react"

import { BrandLogo } from "@/components/brand"
import { VanishingWord } from "@/components/vanishing-word"
import { cn } from "@/lib/utils"

type View = "signin" | "request" | "requested"

/*
  Everything below is drawn from the scanner itself — the catalogs in `data/`,
  LOOKBACK_OPTIONS, and the boolean search — so the page cannot drift into
  claiming something the product does not do.
*/

const BOARDS_TOTAL = 18_264

/*
  Ordered largest first, and shaded down a single blue ramp so the bar reads
  as one quantity split six ways rather than six unrelated categories. The
  ramp is the brand's own scale — deep, strong, base, then two tints and the
  existing line colour.
*/
const CATALOG = [
  { name: "Greenhouse", count: 5_748, shade: "#0b39a6" },
  { name: "Workable", count: 3_480, shade: "#0140cc" },
  { name: "Ashby", count: 3_299, shade: "#005afd" },
  { name: "SmartRecruiters", count: 2_377, shade: "#4d84fd" },
  { name: "Lever", count: 2_263, shade: "#86aefe" },
  { name: "Workday", count: 1_097, shade: "#bed3ff" },
]

/*
  Three, not six. The page has one job — sign the owner in, and tell everyone
  else what they are looking at — so it answers only "is it fresh, is it here,
  can I take it". The rest of what ATSift does is visible once you are inside.
*/
const FEATURES = [
  {
    icon: Timer,
    title: "Fresh, by definition",
    body: "Pick a window from 6 to 72 hours. The scan is drawn from it, not filtered after.",
  },
  {
    icon: MapPin,
    title: "US location, confirmed",
    body: "Every posting is screened for a real US location before it reaches you.",
  },
  {
    icon: ShieldCheck,
    title: "OPT blockers, up front",
    body: "Citizenship, clearance and sponsorship clauses are stated in one red line.",
  },
]

export default function LoginPage() {
  return (
    // useSearchParams needs a boundary; the fallback is the same page shell so
    // nothing shifts when it resolves.
    <Suspense fallback={<Page />}>
      <LoginFlow />
    </Suspense>
  )
}

function LoginFlow() {
  const router = useRouter()
  const destination = useSearchParams().get("next") || "/"

  const [view, setView] = useState<View>("signin")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [requestEmail, setRequestEmail] = useState("")
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const emailRef = useRef<HTMLInputElement>(null)
  const requestRef = useRef<HTMLInputElement>(null)

  // Focus only. Clearing the error belongs to `go`, where the switch is
  // actually decided — an effect would be reacting to its own state change.
  useEffect(() => {
    if (view === "signin") emailRef.current?.focus()
    if (view === "request") requestRef.current?.focus()
  }, [view])

  function go(next: View) {
    setView(next)
    setError(null)
  }

  async function post(path: string, body: unknown) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    return { ok: response.ok, data: await response.json().catch(() => ({})) }
  }

  async function signIn(event: React.FormEvent) {
    event.preventDefault()

    if (busy) return

    setBusy(true)
    setError(null)

    const { ok, data } = await post("/api/auth/login", { email, password })

    if (!ok) {
      setBusy(false)
      setError(data.error ?? "Could not sign in.")

      return
    }

    // Let the server-rendered page pick up the new cookie.
    router.replace(destination)
    router.refresh()
  }

  async function requestAccess(event: React.FormEvent) {
    event.preventDefault()

    if (busy) return

    setBusy(true)
    setError(null)

    const { ok, data } = await post("/api/auth/request-access", {
      email: requestEmail,
      note,
    })

    setBusy(false)

    if (!ok) {
      setError(data.error ?? "Could not send that request.")

      return
    }

    go("requested")
  }

  return (
    <Page>
      {view === "signin" && (
        <form onSubmit={signIn} noValidate>
          <h2 className="font-display text-[1.6rem] font-bold tracking-tight">
            Sign in
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            Only owner has access.{" "}
            <button
              type="button"
              onClick={() => go("request")}
              className="rounded font-semibold text-brand underline-offset-2 transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              Request for access
            </button>
          </p>

          <div className="mt-6 flex flex-col gap-3">
            <Field
              ref={emailRef}
              icon={<Mail aria-hidden="true" className="size-[1.05rem]" />}
              type="email"
              name="email"
              label="Email"
              placeholder="you@example.com"
              autoComplete="username"
              value={email}
              onChange={setEmail}
              disabled={busy}
            />

            <div className="relative">
              <Field
                icon={<Lock aria-hidden="true" className="size-[1.05rem]" />}
                type={showPassword ? "text" : "password"}
                name="password"
                label="Password"
                placeholder="Your password"
                autoComplete="current-password"
                value={password}
                onChange={setPassword}
                disabled={busy}
                padEnd
              />
              <button
                type="button"
                onClick={() => setShowPassword((shown) => !shown)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute right-2 top-1/2 grid size-10 -translate-y-1/2 place-items-center rounded-lg text-faint transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                {showPassword ? (
                  <EyeOff aria-hidden="true" className="size-[1.05rem]" />
                ) : (
                  <Eye aria-hidden="true" className="size-[1.05rem]" />
                )}
              </button>
            </div>
          </div>

          {error && <Problem>{error}</Problem>}

          <Submit busy={busy} disabled={!email.trim() || !password}>
            {busy ? "Signing in…" : "Sign in"}
            {!busy && <ArrowRight aria-hidden="true" className="size-4" />}
          </Submit>
        </form>
      )}

      {view === "request" && (
        <form onSubmit={requestAccess} noValidate>
          <h2 className="font-display text-[1.6rem] font-bold tracking-tight">
            Request access
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            Leave your email and the owner will get in touch.
          </p>

          <div className="mt-6 flex flex-col gap-3">
            <Field
              ref={requestRef}
              icon={<Mail aria-hidden="true" className="size-[1.05rem]" />}
              type="email"
              name="request-email"
              label="Your email"
              placeholder="you@example.com"
              autoComplete="email"
              value={requestEmail}
              onChange={setRequestEmail}
              disabled={busy}
            />

            <label className="block">
              <span className="sr-only">Message</span>
              <textarea
                name="note"
                rows={3}
                maxLength={600}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                disabled={busy}
                placeholder="Anything the owner should know (optional)"
                className={cn(
                  "w-full resize-none rounded-xl border border-line bg-surface-2 px-4 py-3 text-base leading-relaxed sm:text-sm",
                  "transition-colors placeholder:text-faint",
                  "focus-visible:border-brand focus-visible:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/25",
                  "disabled:cursor-not-allowed disabled:opacity-60",
                )}
              />
            </label>
          </div>

          {error && <Problem>{error}</Problem>}

          <Submit busy={busy} disabled={!requestEmail.trim()}>
            {busy ? "Sending…" : "Send request"}
            {!busy && <Send aria-hidden="true" className="size-4" />}
          </Submit>

          <button
            type="button"
            onClick={() => go("signin")}
            className="mt-4 inline-flex items-center gap-1.5 rounded text-sm font-medium text-faint transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <ArrowLeft aria-hidden="true" className="size-3.5" />
            Back to sign in
          </button>
        </form>
      )}

      {view === "requested" && (
        <div>
          <span
            aria-hidden="true"
            className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand"
          >
            <CheckCircle2 className="size-6" />
          </span>
          <h2 className="mt-4 font-display text-[1.6rem] font-bold tracking-tight">
            Request sent
          </h2>
          <p className="mt-1.5 text-pretty text-sm leading-relaxed text-muted">
            The owner has your email and will reach out if they open an account
            for you.
          </p>

          <button
            type="button"
            onClick={() => {
              setRequestEmail("")
              setNote("")
              go("signin")
            }}
            className="mt-6 inline-flex min-h-12 items-center gap-1.5 rounded-xl border border-line bg-surface px-5 text-sm font-semibold transition-colors hover:border-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
          >
            <ArrowLeft aria-hidden="true" className="size-3.5" />
            Back to sign in
          </button>
        </div>
      )}
    </Page>
  )
}

/*
  Two jobs on one page. The owner signs in constantly and wants the form
  immediately; anyone else has never heard of this and needs the argument. So
  the card leads on narrow screens and sits in a sticky column beside the
  story on wide ones — nobody has to scroll past the other person's content.
*/
function Page({ children }: { children?: React.ReactNode }) {
  return (
    <div className="min-h-dvh">
      <header className="border-b border-line">
        <div className="mx-auto flex min-h-16 w-full max-w-[84rem] items-center gap-3 px-5 sm:px-8">
          <BrandLogo />
          <span className="label ml-auto hidden sm:inline">
            Private workspace
          </span>
        </div>
      </header>

      <main className="grid-paper">
        <div className="mx-auto grid w-full max-w-[84rem] gap-x-14 gap-y-12 px-5 py-10 sm:px-8 sm:py-14 lg:grid-cols-[minmax(0,1fr)_25rem] lg:items-start lg:py-20">
          {/* Order flips at lg: story left, card right. */}
          <div className="stagger order-2 flex flex-col gap-12 lg:order-1 lg:gap-14">
            <Hero />
            <Features />
            <Coverage />
          </div>

          <div className="order-1 lg:order-2 lg:sticky lg:top-20">
            <div className="rounded-[1.25rem] border border-line bg-surface p-6 shadow-[0_4px_28px_rgba(8,12,20,0.08)] sm:p-7">
              {children ?? (
                <div className="grid h-72 place-items-center">
                  <Loader2
                    aria-hidden="true"
                    className="size-5 animate-spin text-faint"
                  />
                </div>
              )}

              <DemoLink />
            </div>

            <p className="mt-4 px-1 text-xs leading-relaxed text-faint">
              Signing in lasts 30 days and signing out ends it everywhere. The
              demo account expires after 2 hours.
            </p>
          </div>
        </div>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex w-full max-w-[84rem] flex-col gap-2 px-5 py-6 text-xs text-faint sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <span translate="no">ATSift</span>
          <span>
            Greenhouse · Ashby · Lever · SmartRecruiters · Workable · Workday
          </span>
        </div>
      </footer>
    </div>
  )
}

/*
  The way in for everyone who is not the owner.

  Sits under the form in the card itself, so it is visible in every state —
  including right after someone submits an access request, which is exactly
  the moment they have nothing else to do.

  It points at a separate deployment whose screening runs on a hosted Llama
  model rather than a local one, which is why that build can scan on demand
  and this one falls back to a packaged sample.
*/
function DemoLink() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function enterDemo() {
    if (busy) return

    setBusy(true)
    setError(null)

    const response = await fetch("/api/auth/demo", { method: "POST" })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))

      setBusy(false)
      setError(data.error ?? "Could not start the demo.")

      return
    }

    router.replace("/")
    router.refresh()
  }

  return (
    <div className="mt-6 border-t border-line-soft pt-5">
      <button
        type="button"
        onClick={enterDemo}
        disabled={busy}
        className={cn(
          "flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold",
          "bg-brand text-brand-ink transition-colors hover:bg-brand-strong",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
          "disabled:cursor-wait disabled:opacity-70",
        )}
      >
        {busy ? (
          <Loader2 aria-hidden="true" className="size-4 animate-spin" />
        ) : (
          <UserRound aria-hidden="true" className="size-4" />
        )}
        {busy ? "Opening…" : "Demo account"}
      </button>

      <p className="mt-2 text-center text-xs leading-relaxed text-faint">
        Browse everything here, no password. Read-only.
      </p>

      {error && <Problem>{error}</Problem>}

      <a
        href="https://beone-theta.vercel.app/"
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          "group mt-4 flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border px-4 text-sm font-semibold",
          "border-brand-line bg-brand-soft text-brand-deep transition-colors",
          "hover:border-brand hover:bg-brand hover:text-brand-ink",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        )}
      >
        <PlayCircle aria-hidden="true" className="size-4" />
        Try Software roles Live demo
        <ArrowUpRight
          aria-hidden="true"
          className="size-3.5 transition-transform group-hover:-translate-y-px group-hover:translate-x-px"
        />
      </a>

      <p className="mt-2.5 text-center text-xs leading-relaxed text-faint">
        Runs a real scan on a hosted Llama model. No sign-in needed.
      </p>
    </div>
  )
}

function Hero() {
  return (
    <section>
      <p className="label text-brand">The problem</p>

      <h1 className="mt-3 text-balance font-display text-[2.25rem] font-extrabold leading-[1.03] tracking-[-0.035em] sm:text-5xl lg:text-[3.5rem]">
        If you&rsquo;re not in the first 10 applicants, you&rsquo;re{" "}
        <VanishingWord word="invisible" />.
      </h1>

      <p className="mt-5 max-w-[46ch] text-pretty text-base leading-relaxed text-muted sm:text-lg">
        A role gets buried within hours, and almost none of them say up front
        whether the job is really US-based or open to an F-1 candidate. ATSift
        asks you{" "}
        <strong className="font-semibold text-text">how far back to look</strong>{" "}
        and answers both, across every board at once.
      </p>

      <dl className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
        <Stat value={BOARDS_TOTAL.toLocaleString()} label="Company boards" />
        <Stat value="6" label="Hiring systems" />
        <Stat value="6–72h" label="Scan window" />
      </dl>
    </section>
  )
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-4 py-3.5">
      <dt className="label text-[0.625rem]">{label}</dt>
      <dd className="mt-1.5 font-display text-2xl font-bold tabular-nums tracking-tight text-brand-deep sm:text-[1.75rem]">
        {value}
      </dd>
    </div>
  )
}

function Features() {
  return (
    <section>
      <p className="label text-brand">What it does</p>

      <ul className="mt-4 grid gap-3 sm:grid-cols-3 sm:gap-4">
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <li
            key={title}
            className="rounded-xl border border-line bg-surface p-5 transition-colors hover:border-brand-line"
          >
            <span
              aria-hidden="true"
              className="grid size-9 place-items-center rounded-lg bg-brand-soft text-brand"
            >
              <Icon className="size-[1.15rem]" />
            </span>
            <h2 className="mt-3.5 font-display text-base font-bold tracking-tight">
              {title}
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">{body}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Coverage() {
  return (
    /*
      One strip, not a section. The bar carries the shape of the catalog —
      Greenhouse is nearly a third of it, Workday a sixteenth — and the legend
      names the parts. Anything more about the catalog belongs inside the app,
      not on the door.

      The bar is decorative; every number in it is also in the legend, which is
      what a screen reader reads.
    */
    <section>
      <p className="label text-brand">
        Coverage · {BOARDS_TOTAL.toLocaleString()} boards
      </p>

      <div
        aria-hidden="true"
        className="mt-4 flex h-2.5 w-full overflow-hidden rounded-full bg-surface-2"
      >
        {CATALOG.map((source) => (
          <span
            key={source.name}
            style={{
              width: `${(source.count / BOARDS_TOTAL) * 100}%`,
              backgroundColor: source.shade,
            }}
          />
        ))}
      </div>

      {/*
        A grid, not wrap: free-flowing items left "Workday" orphaned on a line
        of its own. Three columns divide six evenly.
      */}
      <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-2.5 sm:grid-cols-3">
        {CATALOG.map((source) => (
          <div key={source.name} className="flex items-baseline gap-2">
            <span
              aria-hidden="true"
              className="size-2 shrink-0 translate-y-px rounded-full"
              style={{ backgroundColor: source.shade }}
            />
            <dt className="min-w-0 flex-1 truncate text-sm font-medium">
              {source.name}
            </dt>
            <dd className="font-mono text-xs tabular-nums text-faint">
              {source.count.toLocaleString()}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function Field({
  ref,
  icon,
  label,
  value,
  onChange,
  padEnd,
  ...rest
}: {
  ref?: React.Ref<HTMLInputElement>
  icon: React.ReactNode
  label: string
  value: string
  onChange: (value: string) => void
  padEnd?: boolean
} & Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "value" | "onChange" | "className"
>) {
  return (
    <label className="block">
      <span className="sr-only">{label}</span>
      <span className="relative block">
        <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-faint">
          {icon}
        </span>
        <input
          ref={ref}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className={cn(
            "min-h-12 w-full rounded-xl border border-line bg-surface-2 pl-11 text-base sm:text-sm",
            "transition-colors placeholder:text-faint",
            "focus-visible:border-brand focus-visible:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/25",
            "disabled:cursor-not-allowed disabled:opacity-60",
            padEnd ? "pr-14" : "pr-4",
          )}
          {...rest}
        />
      </span>
    </label>
  )
}

function Problem({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="alert"
      className="mt-4 flex items-start gap-2 rounded-xl border border-danger-line bg-danger-bg px-4 py-3 text-sm font-medium leading-snug text-danger"
    >
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      {children}
    </p>
  )
}

function Submit({
  busy,
  disabled,
  children,
}: {
  busy: boolean
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="submit"
      disabled={busy || disabled}
      className={cn(
        "mt-5 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-5 text-sm font-semibold",
        "bg-brand text-brand-ink transition-colors hover:bg-brand-strong",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:bg-line disabled:text-faint",
      )}
    >
      {busy && <Loader2 aria-hidden="true" className="size-4 animate-spin" />}
      {children}
    </button>
  )
}
