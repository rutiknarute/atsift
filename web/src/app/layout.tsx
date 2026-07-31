import type { Metadata, Viewport } from "next"
import { Inter, Inter_Tight, JetBrains_Mono } from "next/font/google"

import "./globals.css"

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
})

const interTight = Inter_Tight({
  variable: "--font-inter-tight",
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
})

const monoLabel = JetBrains_Mono({
  variable: "--font-mono-label",
  subsets: ["latin"],
  weight: ["400", "500"],
})

export const metadata: Metadata = {
  title: "ATSift — fresh roles, on your timeframe",
  description:
    "Sweep verified company job boards for fresh non-senior roles, with US-location and OPT screening.",
}

export const viewport: Viewport = {
  themeColor: "#f5f7fc",
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} ${interTight.variable} ${monoLabel.variable}`}
      >
        {children}
      </body>
    </html>
  )
}
