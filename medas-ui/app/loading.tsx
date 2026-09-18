import { ChatHeader } from "@/components/chat/chat-header"

// Next wraps page.tsx in a Suspense boundary with this as the fallback, so
// the shell paints while the greeting is in flight. It mirrors the page's
// rails and header exactly to keep the swap free of layout shift.
export default function Loading() {
  return (
    <div className="app-backdrop flex h-dvh w-full flex-col items-center bg-fixed sm:p-4 md:p-6">
      <main className="border-border/70 bg-background/95 flex h-full w-full max-w-3xl flex-col overflow-hidden backdrop-blur sm:rounded-2xl sm:border sm:shadow-xl">
        <ChatHeader />

        <div className="min-h-0 flex-1 px-4 py-6 sm:px-6 sm:py-8">
          {/* Skeletons shaped like the first exchange, so the real content
              lands where the placeholder already was. */}
          <div
            className="mx-auto flex w-full max-w-2xl flex-col gap-5"
            role="status"
            aria-label="Loading your conversation"
          >
            <div className="flex items-end gap-2.5">
              <div className="bg-muted size-8 shrink-0 animate-pulse rounded-full" />
              <div className="bg-muted h-11 w-3/5 animate-pulse rounded-2xl rounded-bl-md" />
            </div>
            <div className="flex flex-row-reverse items-end gap-2.5">
              <div className="bg-muted size-8 shrink-0 animate-pulse rounded-full" />
              <div className="bg-muted h-9 w-2/5 animate-pulse rounded-2xl rounded-br-md" />
            </div>
          </div>
        </div>

        <footer className="bg-card/60 shrink-0 border-t px-4 py-3 sm:px-6 sm:py-4">
          <div className="border-border/80 bg-card mx-auto h-13 w-full max-w-2xl animate-pulse rounded-2xl border" />
        </footer>
      </main>
    </div>
  )
}
