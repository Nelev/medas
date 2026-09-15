import { SendHorizontal } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function ChatComposer() {
  return (
    // A real <form> so Enter-to-send works once an onSubmit is attached, and
    // so assistive tech announces it as a form. Unwired for now.
    <form className="flex items-center gap-2">
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
