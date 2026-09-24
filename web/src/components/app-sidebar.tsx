"use client"

import { useState } from "react"
import {
  BarChart3,
  Sparkles,
  PanelLeftClose,
  PanelLeftOpen,
  ScanSearch,
  Settings,
} from "lucide-react"

import { cn } from "@/lib/utils"

const NAV_ITEMS = [
  { label: "For me", icon: Sparkles, key: "for-me" },
  { label: "Scan", icon: ScanSearch, key: "scan" },
  { label: "Analytics", icon: BarChart3, key: "analytics" },
  { label: "Settings", icon: Settings },
]

export function AppSidebar({
  activeSection,
  onSectionChange,
}: {
  activeSection: "scan" | "analytics" | "for-me"
  onSectionChange: (section: "scan" | "analytics" | "for-me") => void
}) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <aside
      className={cn(
        "app-sidebar sticky top-0 z-20 w-full shrink-0 self-start border-b border-line bg-surface/95 p-2 backdrop-blur-xl lg:h-dvh lg:overflow-y-auto lg:border-r lg:border-b-0 lg:px-3 lg:py-5",
        collapsed ? "lg:w-[4.75rem]" : "lg:w-60",
      )}
    >
      <div className={cn("mb-5 hidden lg:flex", collapsed ? "justify-center" : "justify-end")}>
        <button
          type="button"
          aria-label={collapsed ? "Expand sidebar" : "Minimize sidebar"}
          aria-expanded={!collapsed}
          title={collapsed ? "Expand sidebar" : "Minimize sidebar"}
          onClick={() => setCollapsed((value) => !value)}
          className="inline-flex size-10 items-center justify-center rounded-xl text-faint transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {collapsed ? (
            <PanelLeftOpen aria-hidden="true" className="size-5" strokeWidth={1.8} />
          ) : (
            <PanelLeftClose aria-hidden="true" className="size-5" strokeWidth={1.8} />
          )}
        </button>
      </div>

      <nav aria-label="Main navigation" className="flex gap-1 lg:flex-col">
        {NAV_ITEMS.map(({ label, icon: Icon, key }) => {
          const active = key === activeSection

          return (
          <button
            key={label}
            type="button"
            aria-current={active ? "page" : undefined}
            aria-label={key ? label : "Settings — coming soon"}
            disabled={!key}
            title={collapsed ? label : undefined}
            className={cn(
              "flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-2 text-left text-xs font-medium transition-colors disabled:cursor-default disabled:opacity-50 lg:text-sm",
              collapsed ? "lg:justify-center" : "lg:justify-start lg:gap-4 lg:px-4",
              active
                ? "bg-brand-soft text-brand"
                : "text-muted hover:bg-surface-2 hover:text-text",
            )}
            onClick={() => key && onSectionChange(key as "scan" | "analytics" | "for-me")}
          >
            <Icon aria-hidden="true" className="size-5 shrink-0" strokeWidth={1.8} />
            <span className={collapsed ? "lg:sr-only" : undefined}>{label}</span>
          </button>
          )
        })}
      </nav>
    </aside>
  )
}
