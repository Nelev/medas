import { AppSidebar } from "@/components/app-sidebar"
import { ChatComposer } from "@/components/chat/chat-composer"
import { ChatHeader } from "@/components/chat/chat-header"
import { ChatMessages } from "@/components/chat/chat-messages"
import { EcgTrace } from "@/components/chat/ecg-trace"
import { LoadErrorToast } from "@/components/chat/load-error-toast"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { auth } from "@clerk/nextjs/server"
import { unstable_rethrow } from "next/navigation"

import { init } from "@/api/init"

// What the page shows when init fails: the greeting an account without a
// name gets (greeting_text in medas-api), and no past conversations.
const FALLBACK: Awaited<ReturnType<typeof init>> = {
  messages: [{ role: "assistant", text: "Hi there, how can I help you?" }],
  conversations: [],
}

// init, or null when it failed: a failure should not take the whole page
// down, so the page renders FALLBACK and a toast instead.
const loadInit = async () => {
  try {
    return await init()
  } catch (error) {
    // Next signals some of its own control flow by throwing (a redirect, a
    // bail-out to dynamic rendering from the session read inside init);
    // those must reach Next rather than be swallowed here.
    unstable_rethrow(error)
    console.error("Failed to load the greeting and conversations", error)
    return null
  }
}

// An async Server Component: the request to medas-api happens on the server,
// so there is no CORS preflight and no empty-list flash on first paint.
// loading.tsx covers the wait.
export default async function Home() {
  // The proxy already sends signed-out visitors to /sign-in; this is the
  // check next to the data, so the page holds even if the matcher changes.
  // Reading the session also makes the page dynamic, so the greeting is
  // fetched per request rather than baked in at build time.
  await auth.protect()

  // The greeting and the sidebar's list come from the same request.
  const data = await loadInit()
  const { messages, conversations } = data ?? FALLBACK

  return (
    // The sidebar is here rather than in the root layout, so the sign-in and
    // sign-up pages stay without it. h-dvh rather than h-screen: dynamic
    // viewport units account for mobile browser chrome, so the composer is
    // not pushed under the address bar.
    <SidebarProvider className="h-dvh min-h-0">
      <AppSidebar conversations={conversations} />

      {/* The backdrop is fixed so it does not scroll with the conversation. */}
      <SidebarInset className="app-backdrop items-center overflow-hidden bg-fixed sm:p-4 md:p-6">
        <EcgTrace />
        {data === null && <LoadErrorToast />}

        {/* A panel rather than a full-bleed page: on a wide screen an unbounded
            column of chat has nothing to sit in, and the border gives the eye
            an edge to track. It goes full-bleed below sm, where a floating
            card would only waste vertical space. */}
        <div className="border-border bg-card/85 relative z-10 flex h-full w-full max-w-3xl flex-col overflow-hidden backdrop-blur-md sm:rounded-[1.75rem] sm:border sm:panel-lit">
          {/* Phones only: there the sidebar is a sheet, closed until this
              opens it. On wider screens its own header carries the toggle. */}
          <ChatHeader leading={<SidebarTrigger className="md:hidden" />} />

          {/* min-h-0 is load-bearing: without it this flex child refuses to
              shrink below its content height and the list never scrolls. */}
          <ScrollArea className="min-h-0 flex-1">
            {/* The list reads from the store, so a sent message shows up
                without a round trip through the server. This component only
                provides the greeting it starts with. */}
            <ChatMessages initialMessages={messages} />
          </ScrollArea>

          <footer className="bg-card/60 shrink-0 border-t px-4 py-3 backdrop-blur-sm sm:px-6 sm:py-4">
            <ChatComposer />
          </footer>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
