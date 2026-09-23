import { ChatMessageProps } from "@/model/ChatMessage"
import { create } from "zustand"
import { combine } from "zustand/middleware"

const useChatStore = create(
  combine(
    {
      conversationId: "",
      // Annotated because `[]` alone infers never[], which nothing can be
      // appended to.
      messages: [] as ChatMessageProps[],
      // The message on its way to the API, shown before the reply lands. Kept
      // apart from messages because the reply carries its stored copy: an
      // optimistic entry in messages would have to be found and replaced on
      // success and removed on failure, and on the first send the reply also
      // carries the greeting, so the list would need replace-not-append logic
      // too. A slot is simply dropped. Null when nothing is in flight.
      pending: null as ChatMessageProps | null,
      // Empty unless the last send failed. In the store rather than in the
      // composer's own state so anything else that sends can set it too.
      error: "",
    },
    // set merges shallowly, so a setter returns only the keys it changes.
    (set) => ({
      // A reply landing, as one update: the id to append to next, the turns
      // it added, and the pending message dropped because the turns carry its
      // stored copy -- separate sets could render a frame with the question
      // twice. Appends to the list as it is now, not as the caller saw it
      // before awaiting.
      receiveTurns: (conversationId: string, turns: ChatMessageProps[]) =>
        set((s) => ({
          conversationId,
          messages: [...s.messages, ...turns],
          pending: null,
        })),
      setPending: (pending: ChatMessageProps | null) => set({ pending }),
      setError: (error: string) => set({ error }),
    }),
  ),
)

export { useChatStore }
