// The Medas mark: a heartbeat line drawn as the letter M. The favicon
// (app/icon.svg) is the same shape with a heavier stroke for 16px.
export function MedasMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <rect width="64" height="64" rx="15" fill="#0f5a52" />
      <polyline
        points="10,41 18,41 24,19 32,42 40,19 46,41 54,41"
        fill="none"
        stroke="#eafaf3"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
