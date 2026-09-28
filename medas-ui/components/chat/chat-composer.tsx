"use client"
import { Paperclip, SendHorizontal, TriangleAlert } from "lucide-react"
import { ChangeEvent, SyntheticEvent, useRef } from "react"
import { toast } from "sonner"

import { ask, uploadPdf } from "@/api/chat"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useChatStore } from "@/store/store"

// The banner's text: what went wrong, then what it cost the user.
const failure = (cause: unknown, fallback: string, consequence: string) =>
  `${cause instanceof Error ? cause.message : fallback} ${consequence}`

export function ChatComposer() {
  const conversationId = useChatStore((s) => s.conversationId)
  const pending = useChatStore((s) => s.pending)
  const error = useChatStore((s) => s.error)
  const receiveTurns = useChatStore((s) => s.receiveTurns)
  const setPending = useChatStore((s) => s.setPending)
  const setError = useChatStore((s) => s.setError)
  const isUploadingDocument = useChatStore((s) => s.isUploadingDocument)
  const setIsUploadingDocument = useChatStore((s) => s.setIsUploadingDocument)
  const fileRef = useRef<HTMLInputElement>(null)

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
        failure(
          cause,
          "Could not send that message.",
          "Your message was not sent.",
        ),
      )
    }
  }

  // Uploads as soon as a file is picked: there is no attachment to hold.
  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget
    const file = input.files?.[0]
    // Reset so picking the same file again still fires a change.
    input.value = ""

    if (!file || isUploadingDocument) return

    const formData = new FormData()
    formData.append("file", file)

    setIsUploadingDocument(true)

    // A snackbar rather than the banner: the banner explains a failed send
    // above the field it came from, and an upload has no such place.
    try {
      await uploadPdf(formData)
      toast.success("Document uploaded")
    } catch (cause) {
      toast.error(
        failure(
          cause,
          "Could not upload that PDF.",
          "Your PDF was not uploaded.",
        ),
      )
    } finally {
      setIsUploadingDocument(false)
    }
  }

  const uploadLabel = isUploadingDocument
    ? "Uploading document..."
    : "Upload document"

  return (
    <div className="mx-auto w-full max-w-2xl">
      {error ? (
        // role="alert" so the failure is announced, not just drawn.
        <p
          role="alert"
          className="border-destructive/25 bg-destructive/8 text-destructive mb-2.5 flex items-start gap-2 rounded-2xl border px-3.5 py-2.5 text-xs"
        >
          <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden />
          <span>{error}</span>
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
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          aria-label="PDF file"
          hidden
          onChange={handleUpload}
        />
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label={uploadLabel}
                aria-busy={isUploadingDocument}
                disabled={pending !== null || isUploadingDocument}
                onClick={() => fileRef.current?.click()}
                className="size-9 shrink-0 rounded-full"
              >
                {isUploadingDocument ? (
                  <Spinner aria-hidden />
                ) : (
                  <Paperclip className="size-4" aria-hidden />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{uploadLabel}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="submit"
                size="icon"
                aria-label="Send message"
                disabled={pending !== null}
                className="bg-primary text-primary-foreground hover:bg-primary/90 shadow-primary/30 size-9 shrink-0 rounded-full shadow-md"
              >
                <SendHorizontal className="size-4" aria-hidden />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Send message</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </form>

      <p className="text-muted-foreground mt-2.5 px-1 text-center text-[0.65rem] leading-relaxed tracking-[0.01em]">
        Medas reads your medical record. It is not a doctor and does not give
        medical advice &mdash; check anything clinical with your care team.
      </p>
    </div>
  )
}
