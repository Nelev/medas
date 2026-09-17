"use client"
import { SendHorizontal } from "lucide-react"
import { FormEvent, SyntheticEvent } from "react"

import { postMessage, startNewConversation } from "@/api/chat"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useChatStore } from "@/store/store"

export function ChatComposer() {
  const conversationId = useChatStore((s) => s.conversationId)
  const messages = useChatStore((s) => s.messages)
  const setConversationId = useChatStore((s) => s.setConversationId)
  const setMessages = useChatStore((s) => s.setMessages)

  const handleSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()

    // Read the form before any await: currentTarget is null once the
    // handler returns, so grabbing it later gives you null.
    const form = event.currentTarget
    const text = String(new FormData(form).get("message") ?? "").trim()

    if (!text) return

    form.reset()

    // No id yet -> this message creates the conversation.
    if (!conversationId) {
      const created = await startNewConversation({ role: "user", text })
      setConversationId(created.conversationId)
      // Replace, don't append: the API seeds the greeting alongside the
      // first message, so its copy is the whole history.
      setMessages(created.messages)
      return
    }

    const stored = await postMessage({ role: "user", text }, conversationId)
    setMessages([...messages, stored])
  }

  return (
    // A real <form> so Enter-to-send works once an onSubmit is attached, and
    // so assistive tech announces it as a form. Unwired for now.
    <form className="flex items-center gap-2" onSubmit={handleSubmit}>
      <Input
        name="message"
        placeholder="Send a message..."
        aria-label="Message"
        autoComplete="off"
        className="flex-1"
      />
      <Button type="submit" size="icon" aria-label="Send message">
        <SendHorizontal className="size-4" aria-hidden />
      </Button>
    </form>
  )
}
