"use client"

import { Suspense, useEffect, useRef, useState } from "react"
import Image from "next/image"
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
  PlayCircle,
  Send,
  UserRound,
} from "lucide-react"

import atsiftMark from "@/assets/atsift-mark.png"
import { BrandLogo } from "@/components/brand"
import { cn } from "@/lib/utils"

type View = "signin" | "request" | "requested"

/*
  Figures come from the scanner itself — the catalogs in `data/` and
  LOOKBACK_OPTIONS — so the panel cannot drift into claiming something the
  product does not do.
*/
const STATS = [
  { value: "18,264", label: "Company boards" },
  { value: "6", label: "Hiring systems" },
  { value: "6–72h", label: "Scan window" },
]

/*
  White is held at 90% on the blue panel, not lower. Measured against
  #005afd: /90 is 4.66:1 and clears AA, /80 is 3.98:1 and does not, and the
  small uppercase labels at /60 were 2.85:1. Hierarchy comes from size and
  weight instead of from fading the text out.
*/
const FEATURES = [
  {
    title: "Fresh, by definition",
    body: "The window you pick drives the scan itself, not a filter applied after it.",
  },
  {
    title: "US location, confirmed",
    body: "Every posting is screened for a real US location before it reaches you.",
  },
  {
    title: "OPT blockers, up front",
    body: "Citizenship, clearance and sponsorship clauses are stated in one red line.",
  },
]

export default function LoginPage() {
  return (
    // useSearchParams needs a boundary; the fallback is the same shell so
    // nothing shifts when it resolves.
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
    <Shell>
      {view === "signin" && (
        <>
          <header>
            <p className="text-lg text-muted">Welcome to</p>
            <h1 className="mt-0.5 font-display text-[2.75rem] font-extrabold leading-none tracking-[-0.03em] text-text">
              ATSift
            </h1>
          </header>

          <form onSubmit={signIn} noValidate className="mt-10">
            <h2 className="sr-only">Sign in</h2>

            <div className="flex flex-col gap-5">
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
                valid={email.includes("@") && email.includes(".")}
              />

              <Field
                icon={<Lock aria-hidden="true" className="size-[1.05rem]" />}
                type={showPassword ? "text" : "password"}
                name="password"
                label="Password"
                placeholder="••••••••••"
                autoComplete="current-password"
                value={password}
                onChange={setPassword}
                disabled={busy}
                action={
                  <button
                    type="button"
                    onClick={() => setShowPassword((shown) => !shown)}
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                    className="grid size-9 place-items-center rounded-lg text-faint transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    {showPassword ? (
                      <EyeOff aria-hidden="true" className="size-[1.05rem]" />
                    ) : (
                      <Eye aria-hidden="true" className="size-[1.05rem]" />
                    )}
                  </button>
                }
              />
            </div>

            <div className="mt-4 flex items-center justify-between gap-3">
              <span className="text-sm text-faint">Only owner has access.</span>
              <button
                type="button"
                onClick={() => go("request")}
                className="rounded text-sm font-semibold text-brand underline-offset-2 transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                Request for access
              </button>
            </div>

            {error && <Problem>{error}</Problem>}

            <Submit busy={busy} disabled={!email.trim() || !password}>
              {busy ? "Signing in…" : "LOGIN"}
              {!busy && <ArrowRight aria-hidden="true" className="size-4" />}
            </Submit>
          </form>

          <DemoActions />
        </>
      )}

      {view === "request" && (
        <form onSubmit={requestAccess} noValidate>
          <h2 className="font-display text-[2rem] font-extrabold leading-tight tracking-[-0.02em]">
            Request access
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            Leave your email and the owner will get in touch.
          </p>

          <div className="mt-8 flex flex-col gap-5">
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
              valid={requestEmail.includes("@") && requestEmail.includes(".")}
            />

            <label className="block">
              <span className="mb-1.5 block text-sm text-faint">Message</span>
              <textarea
                name="note"
                rows={3}
                maxLength={600}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                disabled={busy}
                placeholder="Anything the owner should know (optional)"
                className={cn(
                  "w-full resize-none rounded-lg border border-line bg-surface px-3.5 py-3 text-base leading-relaxed sm:text-sm",
                  "transition-colors placeholder:text-faint",
                  "focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/20",
                  "disabled:cursor-not-allowed disabled:opacity-60",
                )}
              />
            </label>
          </div>

          {error && <Problem>{error}</Problem>}

          <Submit busy={busy} disabled={!requestEmail.trim()}>
            {busy ? "Sending…" : "SEND REQUEST"}
            {!busy && <Send aria-hidden="true" className="size-4" />}
          </Submit>

          <button
            type="button"
            onClick={() => go("signin")}
            className="mt-5 inline-flex items-center gap-1.5 rounded text-sm font-medium text-faint transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
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
          <h2 className="mt-5 font-display text-[2rem] font-extrabold leading-tight tracking-[-0.02em]">
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
            className="mt-7 inline-flex min-h-12 items-center gap-1.5 rounded-lg border border-line bg-surface px-5 text-sm font-semibold transition-colors hover:border-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
          >
            <ArrowLeft aria-hidden="true" className="size-3.5" />
            Back to sign in
          </button>
        </div>
      )}
    </Shell>
  )
}

/*
  Two panels: the form on white, the argument on blue.

  The blue is a single element sitting under the layout and clipped by a
  bezier, so its left edge sweeps into the white column instead of meeting it
  at a straight seam. The curve is defined in objectBoundingBox units, which
  makes it scale with the panel rather than needing pixel coordinates.

  Below `lg` there is no room for two columns, so the panel stops being a
  backdrop and becomes an ordinary block underneath the form — a stranger can
  still read it, and the owner still gets the form first.
*/
function Shell({ children }: { children?: React.ReactNode }) {
  return (
    <div className="relative min-h-dvh bg-surface">
      <svg aria-hidden="true" className="absolute size-0">
        <defs>
          <clipPath id="panel-sweep" clipPathUnits="objectBoundingBox">
            <path d="M0.17,0 C0.03,0.22 0.05,0.55 0.22,0.78 C0.30,0.89 0.36,0.96 0.38,1 L1,1 L1,0 Z" />
          </clipPath>
        </defs>
      </svg>

      <aside
        aria-hidden="true"
        style={{ clipPath: "url(#panel-sweep)" }}
        className="pointer-events-none absolute inset-y-0 right-0 hidden w-[64%] bg-brand lg:block"
      />

      <div className="relative mx-auto grid min-h-dvh w-full max-w-[96rem] lg:grid-cols-[minmax(0,44%)_minmax(0,56%)]">
        <div className="flex flex-col px-6 py-10 sm:px-12 lg:py-14 lg:pl-16 lg:pr-12">
          {/*
            `self-start` matters: this is a flex column, so the default stretch
            would blow the logo to the column's full width while `h-8` held the
            height, squashing the artwork flat.
          */}
          <BrandLogo className="h-8 w-auto self-start" />

          <div className="flex flex-1 flex-col justify-center py-12 lg:py-8">
            <div className="w-full max-w-[26rem]">
              {children ?? (
                <div className="grid h-80 place-items-center">
                  <Loader2
                    aria-hidden="true"
                    className="size-5 animate-spin text-faint"
                  />
                </div>
              )}
            </div>
          </div>

          <p className="text-sm text-faint">
            <span translate="no">ATSift</span> · Greenhouse · Ashby · Lever ·
            SmartRecruiters · Workable · Workday
          </p>
        </div>

        {/* Desktop: sits over the clipped blue. Mobile: its own blue block. */}
        <div
          data-on-brand=""
          className="relative bg-brand px-6 py-12 text-brand-ink sm:px-12 lg:bg-transparent lg:py-14 lg:pl-20 lg:pr-16"
        >
          <Panel />
        </div>
      </div>
    </div>
  )
}

function Panel() {
  return (
    <div className="relative flex h-full flex-col justify-center">
      {/*
        Stands in for the reference's illustration: the brand mark, scaled up
        and dropped almost to nothing, so it reads as texture rather than a
        second logo competing with the one in the header.
      */}
      <Image
        src={atsiftMark}
        alt=""
        aria-hidden="true"
        sizes="520px"
        className="pointer-events-none absolute -bottom-16 -right-10 hidden w-[26rem] max-w-none opacity-[0.07] lg:block"
      />

      <div className="relative max-w-[34rem]">
        <h2 className="font-display text-[1.6rem] font-bold tracking-tight">
          About ATSift
        </h2>
        <p className="mt-3 text-pretty text-[0.95rem] leading-relaxed text-brand-ink/90">
          A role gets buried within hours, and almost none of them say up front
          whether the job is really US-based or open to an F-1 candidate. ATSift
          sweeps every board at once and answers both before you click.
        </p>

        <dl className="mt-8 grid grid-cols-3 gap-4">
          {STATS.map((stat) => (
            <div key={stat.label} className="border-l border-white/25 pl-3.5">
              <dt className="text-[0.7rem] uppercase tracking-[0.08em] text-brand-ink/90">
                {stat.label}
              </dt>
              <dd className="mt-1 font-display text-2xl font-bold tabular-nums">
                {stat.value}
              </dd>
            </div>
          ))}
        </dl>

        <h2 className="mt-10 font-display text-[1.6rem] font-bold tracking-tight">
          Features
        </h2>
        <ul className="mt-4 flex flex-col gap-4">
          {FEATURES.map((feature) => (
            <li key={feature.title} className="flex gap-3">
              <span
                aria-hidden="true"
                className="mt-[0.45rem] size-1.5 shrink-0 rounded-full bg-brand-ink/70"
              />
              <p className="text-[0.95rem] leading-relaxed text-brand-ink/90">
                <span className="font-semibold text-brand-ink">
                  {feature.title}
                </span>{" "}
                — {feature.body}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

/*
  The two ways in that do not need a password. Kept under the form rather than
  beside it, so the owner's path stays the obvious one.
*/
function DemoActions() {
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
    <div className="mt-7 border-t border-line pt-6">
      <p className="text-center text-sm text-muted">
        Don&rsquo;t have an account?
      </p>

      <button
        type="button"
        onClick={enterDemo}
        disabled={busy}
        className={cn(
          "mt-3 flex min-h-12 w-full items-center justify-center gap-2 rounded-lg border px-4 text-sm font-semibold",
          "border-brand-line bg-brand-soft text-brand-deep transition-colors",
          "hover:border-brand hover:bg-brand hover:text-brand-ink",
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

      {error && <Problem>{error}</Problem>}

      <a
        href="https://beone-theta.vercel.app/"
        target="_blank"
        rel="noopener noreferrer"
        className="group mt-3 flex min-h-11 w-full items-center justify-center gap-1.5 rounded-lg text-sm font-semibold text-brand transition-colors hover:text-brand-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
      >
        <PlayCircle aria-hidden="true" className="size-4" />
        Try Software roles Live demo
        <ArrowUpRight
          aria-hidden="true"
          className="size-3.5 transition-transform group-hover:-translate-y-px group-hover:translate-x-px"
        />
      </a>
    </div>
  )
}

/*
  Underlined field, in the reference's style: the line is the control, and it
  turns brand blue on focus. A tick appears once the value looks like an
  address — the same affordance the reference uses to say "this one is fine".
*/
function Field({
  ref,
  icon,
  label,
  value,
  onChange,
  action,
  valid,
  ...rest
}: {
  ref?: React.Ref<HTMLInputElement>
  icon: React.ReactNode
  label: string
  value: string
  onChange: (value: string) => void
  action?: React.ReactNode
  valid?: boolean
} & Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "value" | "onChange" | "className"
>) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm text-faint">{label}</span>
      <span
        className={cn(
          "flex items-center gap-2.5 border-b-2 border-line px-1 pb-1.5",
          "transition-colors focus-within:border-brand",
        )}
      >
        <span className="shrink-0 text-faint">{icon}</span>
        <input
          ref={ref}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className={cn(
            "min-h-10 min-w-0 flex-1 bg-transparent text-base outline-none sm:text-[0.95rem]",
            "placeholder:text-faint disabled:cursor-not-allowed disabled:opacity-60",
          )}
          {...rest}
        />
        {action}
        {valid && !action && (
          <CheckCircle2 aria-hidden="true" className="size-5 shrink-0 text-brand" />
        )}
      </span>
    </label>
  )
}

function Problem({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="alert"
      className="mt-4 flex items-start gap-2 rounded-lg border border-danger-line bg-danger-bg px-3.5 py-2.5 text-sm font-medium leading-snug text-danger"
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
        "mt-7 inline-flex min-h-[3.25rem] w-full items-center justify-center gap-2 rounded-lg px-5",
        "text-sm font-bold tracking-[0.06em]",
        "bg-brand text-brand-ink shadow-[0_6px_18px_rgba(0,90,253,0.28)]",
        "transition-colors hover:bg-brand-strong",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:bg-line disabled:text-faint disabled:shadow-none",
      )}
    >
      {busy && <Loader2 aria-hidden="true" className="size-4 animate-spin" />}
      {children}
    </button>
  )
}
