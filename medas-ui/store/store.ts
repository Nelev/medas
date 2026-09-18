import { ChatMessageProps } from "@/model/ChatMessage"
import { create } from "zustand"
import { combine } from "zustand/middleware"

const useChatStore = create(
  combine(
    {
      conversationId: "",
      // Annotated because `[]` alone infers never[], which nothing can be
      // assigned to -- that is what breaks setMessages.
      messages: [] as ChatMessageProps[],
      // Empty unless the last send failed. In the store rather than in the
      // composer's own state so anything else that sends can set it too.
      error: "",
    },
    // set merges shallowly, so a setter returns only the key it changes.
    (set) => ({
      setConversationId: (conversationId: string) => set({ conversationId }),
      setMessages: (messages: ChatMessageProps[]) => set({ messages }),
      setError: (error: string) => set({ error }),
    }),
  ),
)

export { useChatStore }
