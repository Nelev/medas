// The heartbeat behind the panel. It was a background-image until now, which
// is why it could not be lit: a background is a texture, with no path inside
// it to travel along. Inline, the same geometry exists once and three things
// share it -- the resting trace, the moving light, and the dot at its head.
//
// No client JS: the sweep is a CSS animation and the dot rides the path with
// SMIL, so this stays a Server Component.

// Six beats. Each is a P wave, the QRS spike, and a T wave, 200 units wide.
const BEAT =
  "h46 q10 -10 20 0 h10 l6 -5 l5 10 l6 -46 l7 82 l7 -41 l6 0 h12 q16 -14 32 0 h43"
const TRACE = `M0 80 ${Array(6).fill(BEAT).join(" ")}`

export function EcgTrace() {
  return (
    // Decorative: it carries no information the reply does not, so it is
    // hidden from assistive tech rather than described to it.
    <div
      className="pointer-events-none absolute inset-x-0 bottom-[6%] z-0 h-44"
      aria-hidden
    >
      <svg
        viewBox="0 0 1200 160"
        preserveAspectRatio="none"
        className="h-full w-full"
      >
        {/* pathLength normalises the path to 1000 units, so the dash values
            below are percentages and stay correct if the waveform changes. */}
        <path id="ecg-path" className="ecg-rest" pathLength={1000} d={TRACE} />
        {/* A <use> rather than a second <path>: one set of coordinates. */}
        <use className="ecg-chaser" href="#ecg-path" />
        {/* mpath points at the same element again -- an offset-path in CSS
            would need the whole waveform copied into the stylesheet. */}
        <circle className="ecg-head" r={3.5}>
          <animateMotion dur="6s" repeatCount="indefinite">
            <mpath href="#ecg-path" />
          </animateMotion>
        </circle>
      </svg>
    </div>
  )
}
