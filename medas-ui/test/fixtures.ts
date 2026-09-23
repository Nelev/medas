import type { ChatMessageProps } from "@/model/ChatMessage"

// The shapes medas-api actually returns. Kept in one place so a change to the
// API contract is a one-file edit here rather than a hunt through specs.
const CONVERSATION_ID = "ba5aa00a-eaac-440f-826a-886354f9babf"

const greeting = {
  role: "assistant" as const,
  text: "Hi Mattia, how can I help you?",
  message_id: "9f1c0e6a-2d17-4a1e-8f2c-0b7d5a9e4c31",
  timestamp: "2026-09-18T09:47:11.120000+00:00",
}

const firstMessage = {
  role: "user" as const,
  text: "Do I have any allergies?",
  message_id: "1b8e77c4-5a03-4e0d-9d2f-6c4a1e8b0f72",
  timestamp: "2026-09-18T09:47:11.124000+00:00",
}

// firstMessage as the composer holds it before the API has stored it: no id
// or timestamp yet.
const pendingMessage = { role: firstMessage.role, text: firstMessage.text }

const storedMessage = {
  role: "user" as const,
  text: "And my medications?",
  message_id: "3d5f91a2-7c64-4b8e-a0d1-2f9c6b3e5478",
  timestamp: "2026-09-18T09:48:02.004000+00:00",
}

// The agent's answer to storedMessage. It carries a severity: both POST
// routes run the triage agent and store the code it assigned, and the badge
// in chat-message.tsx renders from it.
const storedReply = {
  role: "assistant" as const,
  text: "Your record lists a severe NSAID allergy.",
  message_id: "c47a2e91-6b38-4d5f-9e10-8a2c7f4b3d65",
  timestamp: "2026-09-18T09:48:09.512000+00:00",
  // as const, or this widens to string and stops matching Severity.
  severity: "S3" as const,
  confidence: "moderate",
}

const createdConversation = {
  conversation_id: CONVERSATION_ID,
  messages: [greeting, firstMessage],
}

// What /ask answers with: the turn as stored, and the reply to it.
const askedTurns = {
  conversation_id: CONVERSATION_ID,
  messages: [storedMessage, storedReply],
}

// A fetch Response is only ever consumed here through ok/status/json(), so a
// stub with those three is enough and keeps the failure cases readable.
const jsonResponse = (body: unknown, status = 200) =>
  ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }) as Response

const asChatMessage = (message: ChatMessageProps) => message

export {
  CONVERSATION_ID,
  greeting,
  firstMessage,
  pendingMessage,
  storedMessage,
  storedReply,
  createdConversation,
  askedTurns,
  jsonResponse,
  asChatMessage,
}
