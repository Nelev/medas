import { AppShell } from "@/components/app-shell"
import { Sidebar, SidebarContent, SidebarHeader } from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"

// Fixed rather than random, as shadcn's menu skeleton picks them: this is
// rendered on the server, and a random width would not survive hydration.
const ROW_WIDTHS = ["72%", "58%", "84%", "64%", "76%"]

// The sidebar's shape before its list arrives: the new conversation button
// beside the toggle, and a handful of rows.
const SidebarSkeleton = () => (
  <Sidebar collapsible="icon">
    <SidebarHeader className="flex-row items-center gap-1.5 px-3 pt-3.5">
      <Skeleton className="h-9 flex-1" />
      <Skeleton className="size-7" />
    </SidebarHeader>
    <SidebarContent className="gap-0.5 px-3 pt-3">
      <Skeleton className="mb-2 ml-2.5 h-3 w-24" />
      {ROW_WIDTHS.map((width) => (
        <div key={width} className="flex h-9 items-center px-2.5">
          <Skeleton className="h-3.5" style={{ width }} />
        </div>
      ))}
    </SidebarContent>
  </Sidebar>
)

// Next wraps page.tsx in a Suspense boundary with this as the fallback, so
// the shell paints while the greeting is in flight. The frame is the page's
// own AppShell; only what fills it is a placeholder.
export default function Loading() {
  return (
    <AppShell sidebar={<SidebarSkeleton />}>
      <div className="min-h-0 flex-1 px-4 py-6 sm:px-6 sm:py-8">
        {/* Skeletons shaped like the first exchange, so the real content
            lands where the placeholder already was. */}
        <div
          className="mx-auto flex w-full max-w-2xl flex-col gap-6"
          role="status"
          aria-label="Loading your conversation"
        >
          <div className="flex items-end gap-2.5">
            <Skeleton className="size-8 shrink-0 rounded-full" />
            <Skeleton className="bg-secondary h-11 w-3/5 rounded-2xl rounded-bl-md" />
          </div>
          <div className="flex flex-row-reverse items-end gap-2.5">
            <Skeleton className="size-8 shrink-0 rounded-full" />
            <Skeleton className="h-9 w-2/5 rounded-2xl rounded-br-md" />
          </div>
        </div>
      </div>

      <footer className="bg-card/60 shrink-0 border-t px-4 py-3 sm:px-6 sm:py-4">
        <Skeleton className="border-border bg-card mx-auto h-12 w-full max-w-2xl rounded-full border" />
      </footer>
    </AppShell>
  )
}
