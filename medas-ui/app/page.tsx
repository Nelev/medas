import { ChatComposer } from "@/components/chat/chat-composer"
import {
  ChatMessage,
  type ChatMessageProps,
} from "@/components/chat/chat-message"
import { ScrollArea } from "@/components/ui/scroll-area"

// Placeholder content only -- nothing here is wired to the API yet.
const MESSAGES: ChatMessageProps[] = [
  {
    role: "assistant",
    content: "Hello, how can I help you today?",
  },
  {
    role: "user",
    content: "Share my clinical notes",
  },
]

export default function Home() {
  return (
    // h-dvh rather than h-screen: dynamic viewport units account for mobile
    // browser chrome, so the composer is not pushed under the address bar.
    <div className="mx-auto flex h-dvh w-full max-w-3xl flex-col border-x border-border/60">
      <header className="shrink-0 border-b px-4 py-3 sm:px-6">
        <h1 className="text-sm font-medium">Medas</h1>
        <p className="text-xs text-muted-foreground">
          Personal medical assistant
        </p>
      </header>

      {/* min-h-0 is load-bearing: without it this flex child refuses to shrink
          below its content height and the list never scrolls. */}
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-4 px-4 py-6 sm:gap-6 sm:px-6">
          {MESSAGES.map((message, index) => (
            <ChatMessage key={index} role={message.role} content={message.content} />
          ))}
        </div>
      </ScrollArea>
      <footer className="bg-background shrink-0 border-t px-4 py-3 sm:px-6">
        <ChatComposer />
      </footer>
    </div>
  )
}
