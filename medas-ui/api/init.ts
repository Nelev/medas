import { authorization } from "@/api/session"
import { ChatMessageProps } from "@/model/ChatMessage"

// Server-side only: this module is imported from a Server Component, so the
// backend origin never reaches the browser bundle and needs no NEXT_PUBLIC_.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000"

interface InitResponse {
  messages: ChatMessageProps[]
}

// Who the greeting addresses is the API's to read from the session token.
const init = async (): Promise<InitResponse> => {
  const response = await fetch(`${API_BASE_URL}/`, {
    headers: await authorization(),
  })

  if (!response.ok) {
    throw new Error(`Failed to init profile (${response.status})`)
  }

  const data: InitResponse = await response.json()

  return data
}

export { init }
