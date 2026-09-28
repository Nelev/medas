import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs"
import { Stethoscope } from "lucide-react"

import { Button } from "@/components/ui/button"
import { SidebarTrigger } from "@/components/ui/sidebar"

export function ChatHeader() {
  return (
    <header className="bg-card/80 flex shrink-0 items-center gap-3 border-b px-4 py-3.5 backdrop-blur-sm sm:px-5">
      {/* Phones only: there the sidebar is a sheet, closed until this opens
          it. On wider screens its own header carries the toggle. */}
      <SidebarTrigger className="md:hidden" />

      <div className="bg-primary text-primary-foreground shadow-primary/25 flex size-9.5 shrink-0 items-center justify-center rounded-[0.9rem] shadow-md">
        <Stethoscope className="size-4.5" aria-hidden />
      </div>

      <div className="min-w-0 flex-1">
        {/* The serif is the whole brand gesture: one word, set in a face no
            other part of the interface uses. */}
        <h1 className="font-display text-[1.3125rem] leading-none tracking-[-0.01em]">
          Medas
        </h1>
        <p className="text-muted-foreground mt-1 truncate text-xs">
          Personal medical assistant
        </p>
      </div>

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
