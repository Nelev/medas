import { ChatComposer } from "@/components/chat/chat-composer"
import { ChatHeader } from "@/components/chat/chat-header"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ChatMessage } from "@/components/chat/chat-message"
import { init } from "@/api/init"

// Hardcoded until there is a session to read it from. One constant so there
// is a single place to change when auth lands.
const USER = "pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"

// An async Server Component: the request to medas-api happens on the server,
// so there is no CORS preflight and no empty-list flash on first paint. The
// uncached fetch marks this route dynamic; loading.tsx covers the wait.
export default async function Home() {
  const { messages } = await init(USER)

  return (
    // h-dvh rather than h-screen: dynamic viewport units account for mobile
    // browser chrome, so the composer is not pushed under the address bar.
    <div className="mx-auto flex h-dvh w-full max-w-3xl flex-col border-x border-border/60">
      <ChatHeader />

      {/* min-h-0 is load-bearing: without it this flex child refuses to shrink
          below its content height and the list never scrolls. */}
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-4 px-4 py-6 sm:gap-6 sm:px-6">
          {messages.map((message, index) => (
            <ChatMessage key={index} role={message.role} text={message.text} />
          ))}
        </div>
      </ScrollArea>
      <footer className="bg-background shrink-0 border-t px-4 py-3 sm:px-6">
        <ChatComposer />
      </footer>
    </div>
  )
}
