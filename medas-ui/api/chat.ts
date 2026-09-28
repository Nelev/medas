"use server"

import { authorization } from "@/api/session"
import { ChatMessageProps } from "@/model/ChatMessage"

// Server Actions: the composer calls these from the browser, but the fetch
// below runs on the Next server. That keeps the API's origin out of the
// bundle -- a NEXT_PUBLIC_ variable is inlined at build time, so a built
// artefact would carry whatever URL the build machine had, and the browser
// would be calling the API cross-origin. Read here at request time instead,
// so one build runs in any environment. It is also why the API needs no CORS.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000"

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

// The fetch and status check every POST shares, whatever its body.
const send = async (url: string, init: RequestInit): Promise<Response> => {
  const response = await fetch(url, { method: "POST", ...init })

  if (!response.ok) {
    throw new Error(`Request to ${url} failed (${response.status})`)
  }

  return response
}

// A POST to a route that answers with the conversation's new turns. The
// conversation goes in the query, and is omitted rather than sent empty when
// there is not one yet. The API answers in snake_case; this is mapped to
// camelCase here so the convention stops at this boundary.
const postTurns = async (
  path: string,
  conversationId: string | undefined,
  init: RequestInit,
): Promise<AskResult> => {
  const url = new URL(`${API_BASE_URL}${path}`)

  if (conversationId) {
    url.searchParams.set("conversationId", conversationId)
  }

  const response = await send(url.toString(), init)

  // As in api/init.ts, this annotates the payload rather than validating it.
  const data: ConversationTurnsResponse = await response.json()

  return { conversationId: data.conversation_id, turns: data.messages }
}

// Asks the agent. Without a conversationId the API starts a conversation and
// seeds the greeting, so the turns that come back are the greeting, the
// question and the answer; with one they are the question and the answer.
// Either way they are what this request added, and the caller appends them.
//
// A 404 on an id that was supplied means the conversation is unknown,
// soft-deleted or not this user's -- never a reason to silently start a new one, which is why
// the id is omitted rather than guessed at.
const ask = async (
  message: ChatMessageProps,
  conversationId?: string,
): Promise<AskResult> => {
  // A Server Action is a POST endpoint anyone can call, not only this app's
  // composer, so the proxy is not enough on its own: the session is checked
  // here, next to the call it guards, and its token is what the API checks.
  const headers = await authorization()

  // The body is the message itself -- role and text at the top level.
  // Wrapping it in { message } is a 422.
  return postTurns("/ask", conversationId, {
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(message),
  })
}

// Sends a PDF from the composer to the API. The FormData goes through as is,
// and no Content-Type is set, so fetch writes the multipart boundary itself.
// Answers like ask: the upload request and the agent's answer to it, after
// the greeting when it started the conversation.
const uploadPdf = async (
  formData: FormData,
  conversationId?: string,
): Promise<AskResult> => {
  const headers = await authorization()

  return postTurns("/documents", conversationId, { headers, body: formData })
}

export { ask, uploadPdf }
export type { AskResult, StoredMessage }
