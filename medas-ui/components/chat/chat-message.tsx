import { Bot, User } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"

export type ChatRole = "user" | "assistant"

export interface ChatMessageProps {
  role: ChatRole
  content: string
}

export function ChatMessage({ role, content }: ChatMessageProps) {
  const isUser = role === "user"

  return (
    <div
      className={cn(
        "flex w-full items-start gap-2 sm:gap-3",
        // Reversing the row is what moves the user's messages to the right,
        // so the bubble and avatar stay in one markup order.
        isUser && "flex-row-reverse",
      )}
    >
      <Avatar className="size-8 shrink-0">
        <AvatarFallback className="bg-muted text-muted-foreground">
          {isUser ? (
            <User className="size-4" aria-hidden />
          ) : (
            <Bot className="size-4" aria-hidden />
          )}
        </AvatarFallback>
      </Avatar>

      <div
        className={cn(
          // Capped width so a long message wraps into a column instead of
          // stretching the full width of a desktop viewport.
          "max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
          isUser
            ? "rounded-br-sm bg-primary text-primary-foreground"
            : "rounded-bl-sm bg-muted text-foreground",
        )}
      >
        {/* break-words stops an unbroken URL from forcing a horizontal scrollbar. */}
        <p className="whitespace-pre-wrap break-words">{content}</p>
      </div>
    </div>
  )
}
