import { authorization } from "@/api/session"
import { ChatMessageProps } from "@/model/ChatMessage"
import { ConversationSummary } from "@/model/Conversation"

// Server-side only: this module is imported from a Server Component, so the
// backend origin never reaches the browser bundle and needs no NEXT_PUBLIC_.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000"

// The API answers in snake_case; mapped to camelCase below so the convention
// stops at this boundary, as in api/chat.ts.
interface InitResponse {
  messages: ChatMessageProps[]
  conversations: { conversation_id: string }[]
}

interface InitResult {
  messages: ChatMessageProps[]
  conversations: ConversationSummary[]
}

// The greeting and the sidebar's list of past conversations, newest first,
// in one request. Who is asking is the API's to read from the session token.
const init = async (): Promise<InitResult> => {
  const response = await fetch(`${API_BASE_URL}/`, {
    headers: await authorization(),
  })

  if (!response.ok) {
    throw new Error(`Failed to init profile (${response.status})`)
  }

  const data: InitResponse = await response.json()

  return {
    messages: data.messages,
    conversations: data.conversations.map((c) => ({
      conversationId: c.conversation_id,
    })),
  }
}

export { init }
