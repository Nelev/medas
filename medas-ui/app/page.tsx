import { ChatComposer } from "@/components/chat/chat-composer"
import { ChatHeader } from "@/components/chat/chat-header"
import { ChatMessages } from "@/components/chat/chat-messages"
import { EcgTrace } from "@/components/chat/ecg-trace"
import { ScrollArea } from "@/components/ui/scroll-area"
import { connection } from "next/server"

import { init } from "@/api/init"

// Hardcoded until there is a session to read it from. One constant so there
// is a single place to change when auth lands.
const USER = "pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"

// An async Server Component: the request to medas-api happens on the server,
// so there is no CORS preflight and no empty-list flash on first paint.
// loading.tsx covers the wait.
export default async function Home() {
  // Stops prerendering here, so the greeting is fetched per request rather
  // than once at build time. Baking it would serve every visitor whatever
  // the build machine happened to fetch, and would make `next build` require
  // a reachable medas-api. connection() rather than `export const dynamic`:
  // Next 16 prefers it, tying the boundary to the incoming request. Once a
  // session is read here, cookies() makes the page dynamic on its own and
  // this line can go.
  await connection()

  const { messages } = await init(USER)

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
        <ChatHeader patient={USER} />

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
