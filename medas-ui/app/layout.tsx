import type { Metadata } from "next"
import {
  Instrument_Sans,
  Instrument_Serif,
  JetBrains_Mono,
} from "next/font/google"
import "./globals.css"

// Instrument Sans and Instrument Serif are drawn as a pair, so the wordmark
// and the interface agree without any tuning.
const instrumentSans = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin"],
})

// One weight is all it ships, and all the wordmark needs.
const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
})

// For record ids and timestamps: a chart id should look like data.
const jetBrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: "Medas",
  description: "Medas is a modern medical assistant system.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // Light by default. The dark tokens are complete and switching is one
    // class on this element, but the porcelain mode is the designed one.
    <html
      lang="en"
      className={`${instrumentSans.variable} ${instrumentSerif.variable} ${jetBrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  )
}
