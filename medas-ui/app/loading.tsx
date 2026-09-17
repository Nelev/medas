import { ChatHeader } from "@/components/chat/chat-header"

// Next wraps page.tsx in a Suspense boundary with this as the fallback, so
// the shell paints while /init is in flight. It mirrors the page's rails and
// header exactly to keep the swap free of layout shift.
export default function Loading() {
  return (
    <div className="mx-auto flex h-dvh w-full max-w-3xl flex-col border-x border-border/60">
      <ChatHeader />

      <div className="min-h-0 flex-1" />

      <footer className="bg-background shrink-0 border-t px-4 py-3 sm:px-6">
        <p className="text-muted-foreground text-xs" role="status">
          Loading your conversation...
        </p>
      </footer>
    </div>
  )
}
