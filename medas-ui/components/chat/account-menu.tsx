"use client"

import { UserButton } from "@clerk/nextjs"
import { useSyncExternalStore } from "react"

const subscribe = () => () => {}

// Clerk mounts the button into a host div on the client only. If Clerk has
// already loaded by the time React hydrates, that div exists on the client but
// not in the server HTML, so render nothing until hydration has finished.
export function AccountMenu() {
  const hydrated = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  )

  return hydrated ? <UserButton /> : null
}
