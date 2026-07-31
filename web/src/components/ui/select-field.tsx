"use client"

import { ChevronDown } from "lucide-react"

import { cn } from "@/lib/utils"

interface SelectFieldProps {
  label: string
  name?: string
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  hint?: string
  options: { value: string; label: string }[]
  className?: string
}

export function SelectField({
  label,
  name,
  value,
  onChange,
  disabled,
  hint,
  options,
  className,
}: SelectFieldProps) {
  return (
    <label className={cn("flex flex-col gap-1.5", className)}>
      <span className="text-xs font-medium uppercase tracking-wide text-faint">
        {label}
      </span>

      <div className="relative">
        <select
          name={name ?? label.toLowerCase().replace(/\s+/g, "-")}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          className={cn(
            "min-h-11 w-full appearance-none rounded-xl border border-line bg-surface-2",
            "pl-3.5 pr-10 text-sm text-text transition-colors",
            "hover:border-faint",
            "focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/25",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <ChevronDown
          aria-hidden="true"
          className="pointer-events-none absolute right-3.5 top-1/2 size-4 -translate-y-1/2 text-faint"
        />
      </div>

      {hint && <span className="text-xs text-faint">{hint}</span>}
    </label>
  )
}
