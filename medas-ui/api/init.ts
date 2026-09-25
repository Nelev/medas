import { authorization } from "@/api/session"
import { ChatMessageProps } from "@/model/ChatMessage"

// Server-side only: this module is imported from a Server Component, so the
// backend origin never reaches the browser bundle and needs no NEXT_PUBLIC_.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000"

interface InitResponse {
  messages: ChatMessageProps[]
}

// `name` is who the greeting addresses; see greetingName in api/session.ts.
const init = async (name?: string): Promise<InitResponse> => {
  const url = new URL(`${API_BASE_URL}/`)

  if (name) {
    url.searchParams.set("user", name)
  }

  const response = await fetch(url.toString(), {
    headers: await authorization(),
  })

  if (!response.ok) {
    throw new Error(`Failed to init profile (${response.status})`)
  }

  const data: InitResponse = await response.json()

  return data
}

export { init }
