"use client"
import { SendHorizontal, TriangleAlert } from "lucide-react"
import { SyntheticEvent } from "react"

import { postMessage, startNewConversation } from "@/api/chat"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useChatStore } from "@/store/store"

export function ChatComposer() {
  const conversationId = useChatStore((s) => s.conversationId)
  const messages = useChatStore((s) => s.messages)
  const error = useChatStore((s) => s.error)
  const setConversationId = useChatStore((s) => s.setConversationId)
  const setMessages = useChatStore((s) => s.setMessages)
  const setError = useChatStore((s) => s.setError)

  const handleSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()

    // Read the form before any await: currentTarget is null once the
    // handler returns, so grabbing it later gives you null.
    const form = event.currentTarget
    const text = String(new FormData(form).get("message") ?? "").trim()

    if (!text) return

    form.reset()
    // Clear any previous failure: it belonged to the message before this one.
    setError("")

    try {
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
    } catch (cause) {
      // The message was never stored, so nothing is added to the list -- the
      // banner below is the only trace, and without it the send looks like it
      // silently worked.
      setError(
        cause instanceof Error ? cause.message : "Could not send that message.",
      )
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl">
      {error ? (
        // role="alert" so the failure is announced, not just drawn.
        <p
          role="alert"
          className="border-destructive/25 bg-destructive/8 text-destructive mb-2.5 flex items-start gap-2 rounded-2xl border px-3.5 py-2.5 text-xs"
        >
          <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden />
          <span>
            {error}{" "}
            <span className="opacity-80">Your message was not sent.</span>
          </span>
        </p>
      ) : null}

      {/* A real <form> so Enter-to-send works, and so assistive tech
          announces it as a form. The card styling sits on the form itself,
          with the input borderless inside it, so the whole row reads as one
          control and the focus ring surrounds all of it. */}
      <form
        className="border-border bg-card focus-within:border-pulse/40 focus-within:ring-pulse/15 flex items-center gap-2 rounded-full border p-1.5 pl-4 shadow-sm transition-colors focus-within:ring-3"
        onSubmit={handleSubmit}
      >
        <Input
          name="message"
          placeholder="Ask about your medical history..."
          aria-label="Message"
          autoComplete="off"
          className="h-9 flex-1 border-0 bg-transparent px-0 text-[0.9375rem] shadow-none focus-visible:border-0 focus-visible:ring-0"
        />
        <Button
          type="submit"
          size="icon"
          aria-label="Send message"
          className="bg-pulse text-pulse-foreground hover:bg-pulse/90 shadow-pulse/30 size-9 shrink-0 rounded-full shadow-md"
        >
          <SendHorizontal className="size-4" aria-hidden />
        </Button>
      </form>

      <p className="text-muted-foreground mt-2.5 px-1 text-center text-[0.65rem] leading-relaxed tracking-[0.01em]">
        Medas reads your medical record. It is not a doctor and does not give
        medical advice &mdash; check anything clinical with your care team.
      </p>
    </div>
  )
}
