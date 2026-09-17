// Shared by the page and its loading fallback so the two render identical
// chrome -- the title strings and spacing live in one place and cannot drift.
export function ChatHeader() {
  return (
    <header className="shrink-0 border-b px-4 py-3 sm:px-6">
      <h1 className="text-sm font-medium">Medas</h1>
      <p className="text-xs text-muted-foreground">
        Personal medical assistant
      </p>
    </header>
  )
}
