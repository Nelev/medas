import { ChatMessageProps } from "@/model/ChatMessage"

// NEXT_PUBLIC_, unlike api/init.ts: these calls run in the browser (the
// composer is a Client Component), and an unprefixed variable is undefined
// there. That is also why the API needs its CORS middleware.
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

// Hardcoded until there is a session to read it from. The API takes it as a
// query parameter and it must match a row in users, or the insert 404s.
const USER_ID = "7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"

// What the API stores, as opposed to ChatMessageProps which is what the UI
// renders: the id and timestamp are minted server-side and come back with it.
interface StoredMessage extends ChatMessageProps {
  message_id: string
  timestamp: string
}

// The API answers in snake_case; this is mapped to camelCase below so the
// convention stops at this boundary.
interface CreatedConversationResponse {
  conversation_id: string
  messages: StoredMessage[]
}

interface CreatedConversation {
  conversationId: string
  messages: StoredMessage[]
}

const post = async <T>(url: string, body: unknown): Promise<T> => {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    throw new Error(`Request to ${url} failed (${response.status})`)
  }

  // As in api/init.ts, this annotates the payload rather than validating it.
  const data: T = await response.json()

  return data
}

// Starts a conversation. The API seeds the greeting alongside this message,
// so the reply carries the whole history, not just what was sent.
const startNewConversation = async (
  message: ChatMessageProps,
): Promise<CreatedConversation> => {
  const url = `${API_BASE_URL}/conversations?userId=${encodeURIComponent(USER_ID)}`

  // The body is the message itself -- role and text at the top level.
  // Wrapping it in { message } is a 422.
  const data = await post<CreatedConversationResponse>(url, message)

  return { conversationId: data.conversation_id, messages: data.messages }
}

// Appends to an existing conversation. A 404 here means it is unknown or
// soft-deleted -- never a reason to silently start a new one.
const postMessage = async (
  message: ChatMessageProps,
  conversationId: string,
): Promise<StoredMessage> => {
  const url = `${API_BASE_URL}/conversations/${conversationId}/messages`

  return post<StoredMessage>(url, message)
}

export { postMessage, startNewConversation }
export type { CreatedConversation, StoredMessage }
