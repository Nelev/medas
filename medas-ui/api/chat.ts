"use server"

import { ChatMessageProps } from "@/model/ChatMessage"

// Server Actions: the composer calls these from the browser, but the fetch
// below runs on the Next server. That keeps the API's origin out of the
// bundle -- a NEXT_PUBLIC_ variable is inlined at build time, so a built
// artefact would carry whatever URL the build machine had, and the browser
// would be calling the API cross-origin. Read here at request time instead,
// so one build runs in any environment. It is also why the API needs no CORS.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000"

// Hardcoded until there is a session to read it from. The API takes it as a
// query parameter and it must match a row in users, or the insert 404s.
const USER_ID = "7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"

// What the API stores, as opposed to ChatMessageProps which is what the UI
// renders: the id and timestamp are minted server-side and come back with it.
interface StoredMessage extends ChatMessageProps {
  message_id: string
  timestamp: string
}

// The envelope both POST routes answer with: the conversation, and the turns
// this request added to it. Named for the shape rather than for one route.
//
// The API answers in snake_case; this is mapped to camelCase below so the
// convention stops at this boundary.
interface ConversationTurnsResponse {
  conversation_id: string
  messages: StoredMessage[]
}

interface AskResult {
  conversationId: string
  turns: StoredMessage[]
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

// Asks the agent. Without a conversationId the API starts a conversation and
// seeds the greeting, so the turns that come back are the greeting, the
// question and the answer; with one they are the question and the answer.
// Either way they are what this request added, and the caller appends them.
//
// A 404 on an id that was supplied means the conversation is unknown or
// soft-deleted -- never a reason to silently start a new one, which is why
// the id is omitted rather than guessed at.
const ask = async (
  message: ChatMessageProps,
  conversationId?: string,
): Promise<AskResult> => {
  const url = new URL(`${API_BASE_URL}/ask`)
  url.searchParams.set("userId", USER_ID)

  if (conversationId) {
    url.searchParams.set("conversationId", conversationId)
  }

  // The body is the message itself -- role and text at the top level.
  // Wrapping it in { message } is a 422.
  const data = await post<ConversationTurnsResponse>(url.toString(), message)

  return { conversationId: data.conversation_id, turns: data.messages }
}

export { ask }
export type { AskResult, StoredMessage }
