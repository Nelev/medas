"use client"

import { useEffect } from "react"
import { toast } from "sonner"

// A client component only to reach sonner: the page that knows the load
// failed is a Server Component, and toasts are raised in the browser.
export function LoadErrorToast() {
  useEffect(() => {
    toast.error("Couldn't load your conversations. Refresh to try again.")
  }, [])

  return null
}
