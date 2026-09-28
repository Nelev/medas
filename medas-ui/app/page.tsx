import { ChatComposer } from "@/components/chat/chat-composer"
import { ChatHeader } from "@/components/chat/chat-header"
import { ChatMessages } from "@/components/chat/chat-messages"
import { EcgTrace } from "@/components/chat/ecg-trace"
import { ScrollArea } from "@/components/ui/scroll-area"
import { auth } from "@clerk/nextjs/server"

import { init } from "@/api/init"

// An async Server Component: the request to medas-api happens on the server,
// so there is no CORS preflight and no empty-list flash on first paint.
// loading.tsx covers the wait.
export default async function Home() {
  // The proxy already sends signed-out visitors to /sign-in; this is the
  // check next to the data, so the page holds even if the matcher changes.
  // Reading the session also makes the page dynamic, so the greeting is
  // fetched per request rather than baked in at build time.
  await auth.protect()

  const { messages } = await init()

  return (
    // h-dvh rather than h-screen: dynamic viewport units account for mobile
    // browser chrome, so the composer is not pushed under the address bar.
    // The backdrop is fixed so it does not scroll with the conversation.
    <div className="app-backdrop relative flex h-dvh w-full flex-col items-center overflow-hidden bg-fixed sm:p-4 md:p-6">
      {/* A panel rather than a full-bleed page: on a wide screen an unbounded
          column of chat has nothing to sit in, and the border gives the eye
          an edge to track. It goes full-bleed below sm, where a floating card
          would only waste vertical space. */}
      <EcgTrace />

      <main className="border-border bg-card/85 relative z-10 flex h-full w-full max-w-3xl flex-col overflow-hidden backdrop-blur-md sm:rounded-[1.75rem] sm:border sm:panel-lit">
        <ChatHeader />

        {/* min-h-0 is load-bearing: without it this flex child refuses to
            shrink below its content height and the list never scrolls. */}
        <ScrollArea className="min-h-0 flex-1">
          {/* The list reads from the store, so a sent message shows up without
              a round trip through the server. This component only provides the
              greeting it starts with. */}
          <ChatMessages initialMessages={messages} />
        </ScrollArea>

        <footer className="bg-card/60 shrink-0 border-t px-4 py-3 backdrop-blur-sm sm:px-6 sm:py-4">
          <ChatComposer />
        </footer>
      </main>
    </div>
  )
}
