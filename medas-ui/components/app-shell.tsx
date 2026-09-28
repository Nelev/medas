import type { ReactNode } from "react"

import { ChatHeader } from "@/components/chat/chat-header"
import { EcgTrace } from "@/components/chat/ecg-trace"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

interface AppShellProps {
  sidebar: ReactNode
  // Below the header, inside the panel: the conversation and its composer,
  // or their skeletons.
  children: ReactNode
}

// The frame the page and its loading state share, so the swap between them
// is free of layout shift by construction rather than by keeping two copies
// of the same classes in step.
export function AppShell({ sidebar, children }: AppShellProps) {
  return (
    // The sidebar is here rather than in the root layout, so the sign-in and
    // sign-up pages stay without it. h-dvh rather than h-screen: dynamic
    // viewport units account for mobile browser chrome, so the composer is
    // not pushed under the address bar.
    <SidebarProvider className="h-dvh min-h-0">
      {sidebar}

      {/* The backdrop is fixed so it does not scroll with the conversation. */}
      <SidebarInset className="app-backdrop items-center overflow-hidden bg-fixed sm:p-4 md:p-6">
        <EcgTrace />

        {/* A panel rather than a full-bleed page: on a wide screen an unbounded
            column of chat has nothing to sit in, and the border gives the eye
            an edge to track. It goes full-bleed below sm, where a floating
            card would only waste vertical space. */}
        <div className="border-border bg-card/85 relative z-10 flex h-full w-full max-w-3xl flex-col overflow-hidden backdrop-blur-md sm:rounded-[1.75rem] sm:border sm:panel-lit">
          <ChatHeader />
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
