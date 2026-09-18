import { Stethoscope } from "lucide-react"

interface ChatHeaderProps {
  // The record in view. Shown because a clinical tool that does not say whose
  // chart is open is one wrong answer away from a real problem.
  patient?: string
}

export function ChatHeader({ patient }: ChatHeaderProps) {
  return (
    <header className="bg-card/80 flex shrink-0 items-center gap-3 border-b px-4 py-3 backdrop-blur-sm sm:px-5">
      <div className="bg-primary text-primary-foreground flex size-9 shrink-0 items-center justify-center rounded-xl shadow-sm">
        <Stethoscope className="size-4.5" aria-hidden />
      </div>

      <div className="min-w-0 flex-1">
        <h1 className="text-[0.9375rem] leading-tight font-semibold tracking-tight">
          Medas
        </h1>
        <p className="text-muted-foreground truncate text-xs">
          Personal medical assistant
        </p>
      </div>

      {patient ? (
        <span className="border-border/70 bg-background/60 text-muted-foreground hidden items-center gap-1.5 rounded-full border py-1 pr-2.5 pl-2 text-xs sm:inline-flex">
          {/* Not a decorative dot: it says the record is loaded and live. */}
          <span className="bg-primary size-1.5 rounded-full" aria-hidden />
          <span className="text-foreground/80 max-w-[18ch] truncate font-medium">
            {patient}
          </span>
        </span>
      ) : null}
    </header>
  )
}
