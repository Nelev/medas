import type { ChatMessageProps } from "@/model/ChatMessage"

// The shapes medas-api actually returns. Kept in one place so a change to the
// API contract is a one-file edit here rather than a hunt through specs.
const USER_ID = "7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"
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

const storedMessage = {
  role: "user" as const,
  text: "And my medications?",
  message_id: "3d5f91a2-7c64-4b8e-a0d1-2f9c6b3e5478",
  timestamp: "2026-09-18T09:48:02.004000+00:00",
}

const createdConversation = {
  conversation_id: CONVERSATION_ID,
  messages: [greeting, firstMessage],
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
  USER_ID,
  CONVERSATION_ID,
  greeting,
  firstMessage,
  storedMessage,
  createdConversation,
  jsonResponse,
  asChatMessage,
}
