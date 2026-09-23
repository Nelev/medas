"use client"
import { SendHorizontal, TriangleAlert } from "lucide-react"
import { SyntheticEvent } from "react"

import { ask } from "@/api/chat"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useChatStore } from "@/store/store"

export function ChatComposer() {
  const conversationId = useChatStore((s) => s.conversationId)
  const pending = useChatStore((s) => s.pending)
  const error = useChatStore((s) => s.error)
  const receiveTurns = useChatStore((s) => s.receiveTurns)
  const setPending = useChatStore((s) => s.setPending)
  const setError = useChatStore((s) => s.setError)

  const handleSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()

    // Read the form before any await: currentTarget is null once the
    // handler returns, so grabbing it later gives you null.
    const form = event.currentTarget
    const text = String(new FormData(form).get("message") ?? "").trim()

    // One message in flight at a time: there is a single pending slot, and a
    // second send would also race the first for the conversation id.
    if (!text || pending) return

    const message = { role: "user" as const, text }

    form.reset()
    // Clear any previous failure: it belonged to the message before this one.
    setError("")
    // Shown straight away, so the send is visibly acknowledged while the agent
    // works; the stored copy that comes back takes its place.
    setPending(message)

    try {
      // One call whether or not a conversation exists: without an id the
      // API starts one and the greeting comes back among the turns. The
      // store is empty until the first send, so appending then is the same
      // as replacing -- the greeting does not end up rendered twice.
      const result = await ask(message, conversationId)

      receiveTurns(result.conversationId, result.turns)
    } catch (cause) {
      // The message was never stored, so it is taken back out of the list --
      // the banner below is the only trace, and without it the message would
      // just vanish.
      setPending(null)
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
        className="border-border bg-card focus-within:border-primary/40 focus-within:ring-primary/15 flex items-center gap-2 rounded-full border p-1.5 pl-4 shadow-sm transition-colors focus-within:ring-3"
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
          disabled={pending !== null}
          className="bg-primary text-primary-foreground hover:bg-primary/90 shadow-primary/30 size-9 shrink-0 rounded-full shadow-md"
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
