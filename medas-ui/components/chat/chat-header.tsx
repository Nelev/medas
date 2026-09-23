import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs"
import { Stethoscope } from "lucide-react"

import { Button } from "@/components/ui/button"

interface ChatHeaderProps {
  // The record in view. Shown because a clinical tool that does not say whose
  // chart is open is one wrong answer away from a real problem.
  patient?: string
}

export function ChatHeader({ patient }: ChatHeaderProps) {
  return (
    <header className="bg-card/80 flex shrink-0 items-center gap-3 border-b px-4 py-3.5 backdrop-blur-sm sm:px-5">
      <div className="bg-primary text-primary-foreground shadow-primary/25 flex size-9.5 shrink-0 items-center justify-center rounded-[0.9rem] shadow-md">
        <Stethoscope className="size-4.5" aria-hidden />
      </div>

      <div className="min-w-0 flex-1">
        {/* The serif is the whole brand gesture: one word, set in a face no
            other part of the interface uses. */}
        <h1 className="font-display text-[1.3125rem] leading-none tracking-[-0.01em]">
          Medas
        </h1>
        <p className="text-muted-foreground mt-1 truncate text-[0.7rem]">
          Personal medical assistant
        </p>
      </div>

      {patient ? (
        <span className="border-border bg-background/60 text-muted-foreground hidden items-center gap-2 rounded-full border py-1.5 pr-3 pl-2.5 font-mono text-[0.6875rem] sm:inline-flex">
          {/* Not a decorative dot: it says the record is loaded and live, and
              it is the only thing on screen that moves. */}
          <span
            className="bg-pulse pulse-dot relative size-1.5 rounded-full"
            aria-hidden
          />
          <span className="text-foreground/75 max-w-[18ch] truncate">
            {patient}
          </span>
        </span>
      ) : null}

      {/* Signed out, the two ways in; signed in, the account menu. Clerk's
          buttons wrap ours, so they keep the interface's own look. */}
      <Show when="signed-out">
        <div className="flex shrink-0 items-center gap-2">
          <SignInButton>
            <Button variant="ghost" size="sm">
              Sign in
            </Button>
          </SignInButton>
          <SignUpButton>
            <Button size="sm">Sign up</Button>
          </SignUpButton>
        </div>
      </Show>
      <Show when="signed-in">
        <UserButton />
      </Show>
    </header>
  )
}
