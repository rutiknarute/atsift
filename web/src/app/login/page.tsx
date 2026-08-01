"use client"

import { Suspense, useEffect, useRef, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Eye,
  EyeOff,
  Loader2,
  LockKeyhole,
  Mail,
  MapPin,
  PlayCircle,
  ScanSearch,
  Send,
  ShieldCheck,
  UserRound,
} from "lucide-react"

import { BrandLogo } from "@/components/brand"
import { cn } from "@/lib/utils"

type View = "signin" | "request" | "requested"

const STATS = [
  { value: "18,264", label: "Company boards" },
  { value: "6", label: "Hiring systems" },
  { value: "6–72h", label: "Freshness window" },
]

const FEATURES = [
  {
    icon: Clock3,
    title: "Fresh by design",
    body: "Your timeframe drives the scan itself—not a filter added later.",
  },
  {
    icon: MapPin,
    title: "US location checked",
    body: "Every role is screened for a real US location before it appears.",
  },
  {
    icon: ShieldCheck,
    title: "OPT blockers surfaced",
    body: "Sponsorship, citizenship, and clearance clauses stay visible.",
  },
]

function isEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}

export default function LoginPage() {
  return (
    <Suspense fallback={<Shell />}>
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

    try {
      const { ok, data } = await post("/api/auth/login", { email, password })

      if (!ok) {
        setBusy(false)
        setError(data.error ?? "Those credentials did not work. Try again.")
        return
      }

      router.replace(destination)
      router.refresh()
    } catch {
      setBusy(false)
      setError("ATSift could not be reached. Check your connection and retry.")
    }
  }

  async function requestAccess(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return

    setBusy(true)
    setError(null)

    try {
      const { ok, data } = await post("/api/auth/request-access", {
        email: requestEmail,
        note,
      })

      if (!ok) {
        setError(data.error ?? "Your request could not be sent. Try again.")
        return
      }

      go("requested")
    } catch {
      setError("ATSift could not be reached. Check your connection and retry.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell>
      {view === "signin" && (
        <div className="rise">
          <AuthHeading
            eyebrow="Owner workspace"
            title="Welcome back."
            body="Sign in to run a fresh scan and pick up where you left off."
          />

          <form onSubmit={signIn} noValidate className="mt-8">
            <div className="flex flex-col gap-5">
              <Field
                ref={emailRef}
                icon={<Mail aria-hidden="true" className="size-[1.1rem]" />}
                type="email"
                name="email"
                label="Email address"
                placeholder="you@example.com"
                autoComplete="username"
                inputMode="email"
                value={email}
                onChange={setEmail}
                disabled={busy}
                valid={isEmail(email)}
              />

              <Field
                icon={
                  <LockKeyhole aria-hidden="true" className="size-[1.1rem]" />
                }
                type={showPassword ? "text" : "password"}
                name="password"
                label="Password"
                placeholder="Enter your password"
                autoComplete="current-password"
                value={password}
                onChange={setPassword}
                disabled={busy}
                action={
                  <button
                    type="button"
                    onClick={() => setShowPassword((shown) => !shown)}
                    disabled={busy}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                    className="grid size-11 shrink-0 place-items-center rounded-xl text-faint transition-colors duration-200 hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {showPassword ? (
                      <EyeOff aria-hidden="true" className="size-[1.1rem]" />
                    ) : (
                      <Eye aria-hidden="true" className="size-[1.1rem]" />
                    )}
                  </button>
                }
              />
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <span className="inline-flex items-center gap-1.5 text-sm text-faint">
                <LockKeyhole aria-hidden="true" className="size-3.5" />
                Private owner access
              </span>
              <button
                type="button"
                onClick={() => go("request")}
                className="min-h-11 rounded-lg px-1 text-sm font-semibold text-brand underline-offset-4 transition-colors duration-200 hover:text-brand-strong hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
              >
                Request access
              </button>
            </div>

            {error && <Problem>{error}</Problem>}

            <Submit busy={busy} disabled={!isEmail(email) || !password}>
              {busy ? "Signing in…" : "Sign in to ATSift"}
              {!busy && <ArrowRight aria-hidden="true" className="size-4" />}
            </Submit>
          </form>

          <DemoActions />
        </div>
      )}

      {view === "request" && (
        <form onSubmit={requestAccess} noValidate className="rise">
          <BackButton onClick={() => go("signin")} />
          <AuthHeading
            eyebrow="New workspace access"
            title="Request an invite."
            body="Share your email and a short note. The owner will follow up if access is available."
          />

          <div className="mt-8 flex flex-col gap-5">
            <Field
              ref={requestRef}
              icon={<Mail aria-hidden="true" className="size-[1.1rem]" />}
              type="email"
              name="request-email"
              label="Email address"
              placeholder="you@example.com"
              autoComplete="email"
              inputMode="email"
              value={requestEmail}
              onChange={setRequestEmail}
              disabled={busy}
              valid={isEmail(requestEmail)}
            />

            <label className="block" htmlFor="note">
              <span className="mb-2 flex items-center justify-between gap-4 text-sm font-semibold text-text">
                <span>
                  Message <span className="font-normal text-faint">(optional)</span>
                </span>
                <span className="font-normal tabular-nums text-faint">
                  {note.length}/600
                </span>
              </span>
              <textarea
                id="note"
                name="note"
                rows={4}
                maxLength={600}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                disabled={busy}
                placeholder="What would you like to use ATSift for?"
                className={cn(
                  "min-h-28 w-full resize-y rounded-xl border border-line bg-bg/70 px-4 py-3.5 text-base leading-relaxed text-text sm:text-[0.95rem]",
                  "transition-[border-color,box-shadow,background-color] duration-200 placeholder:text-faint",
                  "hover:border-brand-line hover:bg-surface focus-visible:border-brand focus-visible:bg-surface focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/10",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                )}
              />
            </label>
          </div>

          {error && <Problem>{error}</Problem>}

          <Submit busy={busy} disabled={!isEmail(requestEmail)}>
            {busy ? "Sending request…" : "Send request"}
            {!busy && <Send aria-hidden="true" className="size-4" />}
          </Submit>
        </form>
      )}

      {view === "requested" && (
        <div className="rise py-4">
          <span
            aria-hidden="true"
            className="grid size-14 place-items-center rounded-2xl bg-brand-soft text-brand ring-8 ring-brand-soft/50"
          >
            <CheckCircle2 className="size-7" />
          </span>
          <p className="label mt-8 text-brand">Request received</p>
          <h1 className="mt-3 max-w-sm font-display text-3xl font-bold leading-tight tracking-[-0.035em] text-text sm:text-[2.5rem]">
            You&rsquo;re on the list.
          </h1>
          <p className="mt-4 max-w-md text-base leading-relaxed text-muted">
            The owner has your email and will reach out if a workspace becomes
            available.
          </p>

          <button
            type="button"
            onClick={() => {
              setRequestEmail("")
              setNote("")
              go("signin")
            }}
            className="mt-8 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-line bg-surface px-5 text-sm font-semibold text-text transition-[border-color,background-color,box-shadow] duration-200 hover:border-brand-line hover:bg-brand-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
          >
            <ArrowLeft aria-hidden="true" className="size-4" />
            Return to sign in
          </button>
        </div>
      )}
    </Shell>
  )
}

function Shell({ children }: { children?: React.ReactNode }) {
  return (
    <div className="auth-page relative min-h-dvh overflow-hidden px-4 py-5 sm:px-6 sm:py-6 lg:px-8 lg:py-8">
      <div aria-hidden="true" className="auth-orb auth-orb-one" />
      <div aria-hidden="true" className="auth-orb auth-orb-two" />

      <div className="relative mx-auto flex min-h-[calc(100dvh-2.5rem)] w-full max-w-[78rem] flex-col sm:min-h-[calc(100dvh-3rem)] lg:min-h-[calc(100dvh-4rem)]">
        <header className="flex items-center justify-between gap-4 px-1 py-2 sm:px-2">
          <BrandLogo className="h-8 w-auto sm:h-9" />
          <span className="inline-flex min-h-10 items-center gap-2 rounded-full border border-brand-line/80 bg-surface/80 px-3.5 text-xs font-semibold text-brand-deep shadow-sm backdrop-blur-md sm:text-sm">
            <ShieldCheck aria-hidden="true" className="size-4 text-brand" />
            Secure workspace
          </span>
        </header>

        <main className="my-auto grid items-stretch gap-4 py-6 lg:grid-cols-[minmax(0,1.06fr)_minmax(26rem,0.94fr)] lg:gap-5 lg:py-8">
          <section className="order-1 flex min-h-[35rem] items-center rounded-[1.75rem] border border-white/80 bg-surface/90 p-6 shadow-[0_24px_80px_rgba(20,43,88,0.12)] backdrop-blur-xl sm:p-10 lg:order-2 lg:min-h-[40rem] lg:p-12 xl:p-16">
            <div className="mx-auto w-full max-w-[27rem]">
              {children ?? (
                <div className="grid min-h-72 place-items-center" role="status">
                  <Loader2
                    aria-hidden="true"
                    className="size-6 animate-spin text-brand"
                  />
                  <span className="sr-only">Loading sign in</span>
                </div>
              )}
            </div>
          </section>

          <aside className="auth-story relative order-2 min-h-[34rem] overflow-hidden rounded-[1.75rem] p-7 text-white shadow-[0_24px_80px_rgba(8,28,77,0.22)] sm:p-10 lg:order-1 lg:min-h-[40rem] lg:p-12 xl:p-14">
            <ProductStory />
          </aside>
        </main>

      </div>
    </div>
  )
}

function ProductStory() {
  return (
    <div className="relative z-10 flex h-full flex-col">
      <div
        aria-hidden="true"
        className="absolute -right-28 -top-28 size-72 rounded-full bg-brand/45 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="absolute -bottom-24 -left-20 size-64 rounded-full bg-[#377cff]/20 blur-3xl"
      />

      <div className="relative">
        <span className="inline-flex min-h-9 items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3.5 text-xs font-semibold text-white backdrop-blur-sm">
          <ScanSearch aria-hidden="true" className="size-4 text-[#8db7ff]" />
          Built for the early window
        </span>
        <h2 className="mt-7 max-w-xl font-display text-[2.15rem] font-bold leading-[1.08] tracking-[-0.04em] text-balance sm:text-[2.8rem] lg:text-[3rem]">
          Find the roles worth applying to before the crowd does.
        </h2>
        <p className="mt-5 max-w-[34rem] text-base leading-relaxed text-white/75 sm:text-[1.05rem]">
          ATSift scans company career pages directly, then checks freshness,
          location, and OPT fit before a role reaches your list.
        </p>
      </div>

      <div className="relative mt-9 rounded-2xl border border-white/15 bg-white/[0.08] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-md sm:p-5">
        <p className="label text-[#a9c6ff]">What every result answers</p>
        <ul className="mt-4 grid gap-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <li
              key={title}
              className="flex gap-3 rounded-xl border border-white/10 bg-white/[0.05] p-3.5"
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-[#1a61e8] text-white shadow-sm">
                <Icon aria-hidden="true" className="size-[1.05rem]" />
              </span>
              <div>
                <h3 className="text-sm font-semibold text-white">{title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-white/70">{body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <dl className="relative mt-auto grid grid-cols-3 gap-3 pt-9">
        {STATS.map((stat) => (
          <div key={stat.label} className="border-l border-white/20 pl-3 sm:pl-4">
            <dd className="font-display text-xl font-bold tabular-nums text-white sm:text-2xl">
              {stat.value}
            </dd>
            <dt className="mt-1 text-[0.68rem] font-medium uppercase leading-snug tracking-[0.08em] text-white/65 sm:text-xs">
              {stat.label}
            </dt>
          </div>
        ))}
      </dl>
    </div>
  )
}

function AuthHeading({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string
  title: string
  body: string
}) {
  return (
    <header>
      <p className="label text-brand">{eyebrow}</p>
      <h1 className="mt-3 font-display text-3xl font-bold leading-tight tracking-[-0.035em] text-text sm:text-[2.5rem]">
        {title}
      </h1>
      <p className="mt-3 max-w-md text-base leading-relaxed text-muted">{body}</p>
    </header>
  )
}

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mb-8 inline-flex min-h-11 items-center gap-2 rounded-lg pr-2 text-sm font-semibold text-faint transition-colors duration-200 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
    >
      <ArrowLeft aria-hidden="true" className="size-4" />
      Back to sign in
    </button>
  )
}

function DemoActions() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function enterDemo() {
    if (busy) return

    setBusy(true)
    setError(null)

    try {
      const response = await fetch("/api/auth/demo", { method: "POST" })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        setBusy(false)
        setError(data.error ?? "The demo could not be opened. Try again.")
        return
      }

      router.replace("/")
      router.refresh()
    } catch {
      setBusy(false)
      setError("ATSift could not be reached. Check your connection and retry.")
    }
  }

  return (
    <div className="mt-8">
      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-line" />
        <span className="text-xs font-medium uppercase tracking-[0.08em] text-faint">
          Or explore first
        </span>
        <span className="h-px flex-1 bg-line" />
      </div>

      <button
        type="button"
        onClick={enterDemo}
        disabled={busy}
        className={cn(
          "mt-5 flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border px-4 text-sm font-semibold",
          "border-line bg-surface text-text transition-[border-color,background-color,box-shadow] duration-200",
          "hover:border-brand-line hover:bg-brand-soft hover:text-brand-deep",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
          "disabled:cursor-wait disabled:opacity-50",
        )}
      >
        {busy ? (
          <Loader2 aria-hidden="true" className="size-4 animate-spin" />
        ) : (
          <UserRound aria-hidden="true" className="size-4" />
        )}
        {busy ? "Opening demo…" : "Continue with demo account"}
      </button>

      {error && <Problem>{error}</Problem>}

      <a
        href="https://beone-theta.vercel.app/"
        target="_blank"
        rel="noopener noreferrer"
        className="group mt-3 flex min-h-11 w-full items-center justify-center gap-1.5 rounded-lg text-sm font-semibold text-brand transition-colors duration-200 hover:text-brand-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
      >
        <PlayCircle aria-hidden="true" className="size-4" />
        Open the live software-roles demo
        <ArrowUpRight
          aria-hidden="true"
          className="size-3.5 transition-transform duration-200 group-hover:-translate-y-px group-hover:translate-x-px"
        />
      </a>
    </div>
  )
}

function Field({
  ref,
  icon,
  label,
  value,
  onChange,
  action,
  valid,
  name,
  ...rest
}: {
  ref?: React.Ref<HTMLInputElement>
  icon: React.ReactNode
  label: string
  value: string
  onChange: (value: string) => void
  action?: React.ReactNode
  valid?: boolean
  name: string
} & Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "value" | "onChange" | "className" | "name"
>) {
  return (
    <div>
      <label htmlFor={name} className="mb-2 block text-sm font-semibold text-text">
        {label}
      </label>
      <div
        className={cn(
          "flex min-h-[3.25rem] items-center gap-2 rounded-xl border border-line bg-bg/70 pl-4 pr-1.5",
          "transition-[border-color,box-shadow,background-color] duration-200 hover:border-brand-line hover:bg-surface",
          "focus-within:border-brand focus-within:bg-surface focus-within:ring-4 focus-within:ring-brand/10",
        )}
      >
        <span className="shrink-0 text-faint">{icon}</span>
        <input
          ref={ref}
          id={name}
          name={name}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="min-h-12 min-w-0 flex-1 bg-transparent px-1.5 text-base text-text outline-none placeholder:text-faint disabled:cursor-not-allowed disabled:opacity-50 sm:text-[0.95rem]"
          {...rest}
        />
        {action}
        {valid && !action && (
          <span
            aria-label="Valid email address"
            className="mr-2 grid size-7 shrink-0 place-items-center rounded-full bg-brand-soft text-brand"
          >
            <Check aria-hidden="true" className="size-4" strokeWidth={2.5} />
          </span>
        )}
      </div>
    </div>
  )
}

function Problem({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="alert"
      className="mt-4 flex items-start gap-2.5 rounded-xl border border-danger-line bg-danger-bg px-3.5 py-3 text-sm font-medium leading-relaxed text-danger"
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
        "mt-6 inline-flex min-h-[3.25rem] w-full items-center justify-center gap-2 rounded-xl px-5 text-sm font-semibold",
        "bg-brand text-brand-ink shadow-[0_10px_24px_rgba(0,90,253,0.24)] transition-[background-color,box-shadow,transform] duration-200",
        "hover:bg-brand-strong hover:shadow-[0_12px_28px_rgba(0,71,210,0.28)] active:scale-[0.99]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:bg-line disabled:text-faint disabled:shadow-none disabled:active:scale-100",
      )}
    >
      {busy && <Loader2 aria-hidden="true" className="size-4 animate-spin" />}
      {children}
    </button>
  )
}
