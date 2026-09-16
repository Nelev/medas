import { Stethoscope, User } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import {
  Message,
  MessageAvatar,
  MessageContent,
} from "@/components/ui/message"

export type ChatRole = "user" | "assistant"

export interface ChatMessageProps {
  role: ChatRole
  content: string
}

export function ChatMessage({ role, content }: ChatMessageProps) {
  const isUser = role === "user"
  const RoleIcon = isUser ? User : Stethoscope

  return (
    // Rendered with no wrapper element: the list already spaces rows with
    // `gap`, and Message is w-full. A max-width at this level clamps every
    // row -- max-w-sm against the shell's max-w-3xl is what pinned messages
    // to the left half.
    <Message align={isUser ? "end" : "start"}>
      <MessageAvatar>
        <Avatar>
          {/* Icons rather than an image: role is the only thing to convey,
              and there are no avatar assets in public/. */}
          <AvatarFallback>
            <RoleIcon className="size-4" aria-hidden="true" />
            <span className="sr-only">{isUser ? "You" : "Assistant"}</span>
          </AvatarFallback>
        </Avatar>
      </MessageAvatar>
      <MessageContent>
        <Bubble variant={isUser ? "default" : "muted"}>
          <BubbleContent>{content}</BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  )
}
