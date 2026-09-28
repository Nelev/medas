import { ConversationSummary } from "@/model/Conversation"

// STUB: medas-api has no list endpoint yet. The contract this stands in for
// is GET /conversations -> { conversations: [{ conversation_id, title }] },
// newest first; swap this for the fetch once the route lands.
const STUB_CONVERSATIONS: ConversationSummary[] = [
  {
    conversationId: "0b6f2c1e-8d4a-4f7b-9c3e-1a2b3c4d5e6f",
    title: "Do I have any allergies?",
  },
  {
    conversationId: "5e9d7a3b-2c1f-4e8d-b6a4-7f8e9d0c1b2a",
    title: "What were my last blood test results?",
  },
  {
    conversationId: "a3c8e1f4-6b2d-4a9e-8f7c-3d4e5f6a7b8c",
    title: "Which medications am I taking right now?",
  },
]

const listConversations = async (): Promise<ConversationSummary[]> =>
  STUB_CONVERSATIONS

export { listConversations }
