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
    <div className="mx-auto w-full max-w-2xl">
      {/* A real <form> so Enter-to-send works, and so assistive tech
          announces it as a form. The card styling sits on the form itself,
          with the input borderless inside it, so the whole row reads as one
          control and the focus ring surrounds all of it. */}
      <form
        className="border-border/80 bg-card focus-within:border-primary/40 focus-within:ring-ring/15 flex items-center gap-2 rounded-2xl border p-2 shadow-sm transition-colors focus-within:ring-3"
        onSubmit={handleSubmit}
      >
        <Input
          name="message"
          placeholder="Ask about your medical history..."
          aria-label="Message"
          autoComplete="off"
          className="h-9 flex-1 border-0 bg-transparent px-2 shadow-none focus-visible:border-0 focus-visible:ring-0"
        />
        <Button
          type="submit"
          size="icon"
          aria-label="Send message"
          className="size-9 shrink-0 rounded-xl"
        >
          <SendHorizontal className="size-4" aria-hidden />
        </Button>
      </form>

      <p className="text-muted-foreground mt-2 px-1 text-center text-[0.6875rem] leading-relaxed">
        Medas reads your medical record. It is not a doctor and does not give
        medical advice &mdash; check anything clinical with your care team.
      </p>
    </div>
  )
}
