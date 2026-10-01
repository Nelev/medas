import { AppShell } from "@/components/app-shell"
import { AppSidebar } from "@/components/app-sidebar"
import { ChatComposer } from "@/components/chat/chat-composer"
import { ChatMessages } from "@/components/chat/chat-messages"
import { LoadErrorToast } from "@/components/chat/load-error-toast"
import { ScrollArea } from "@/components/ui/scroll-area"
import { auth } from "@clerk/nextjs/server"
import { unstable_rethrow } from "next/navigation"

import { init } from "@/api/init"

// What the page shows when init fails: the greeting an account without a
// name gets (greeting_texts in medas-api), and no past conversations.
const FALLBACK: Awaited<ReturnType<typeof init>> = {
  messages: [
    {
      role: "assistant",
      text: "Hi there, I'm Medas. I answer questions about your own medical record.",
    },
    {
      role: "assistant",
      text: "You can ask me about your conditions, medications, test results or history. You can upload a PDF with the paperclip button and I'll add it to your record if it checks out. And you can ask me to export this conversation as a PDF.",
    },
    { role: "assistant", text: "Where would you like to start?" },
  ],
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
    <AppShell sidebar={<AppSidebar conversations={conversations} />}>
      {data === null && <LoadErrorToast />}

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
    </AppShell>
  )
}
