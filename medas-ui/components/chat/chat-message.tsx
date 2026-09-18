import { Stethoscope, User } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import {
  Message,
  MessageAvatar,
  MessageContent,
} from "@/components/ui/message"
import { ChatMessageProps } from "@/model/ChatMessage"

export function ChatMessage({ role, text }: ChatMessageProps) {
  const isUser = role === "user"
  const RoleIcon = isUser ? User : Stethoscope

  return (
    // Rendered with no wrapper element: the list already spaces rows with
    // `gap`, and Message is w-full. A max-width at this level clamps every
    // row -- max-w-sm against the shell's max-w-3xl is what pinned messages
    // to the left half.
    <Message align={isUser ? "end" : "start"} className="gap-2.5">
      <MessageAvatar className="self-end">
        <Avatar>
          {/* Icons rather than an image: role is the only thing to convey,
              and there are no avatar assets in public/. */}
          <AvatarFallback
            className={
              isUser
                ? "bg-secondary text-muted-foreground"
                : "bg-primary/10 text-primary"
            }
          >
            <RoleIcon className="size-4" aria-hidden="true" />
            <span className="sr-only">{isUser ? "You" : "Assistant"}</span>
          </AvatarFallback>
        </Avatar>
      </MessageAvatar>
      <MessageContent>
        <Bubble variant={isUser ? "default" : "outline"}>
          {/* Asymmetric corners: the squared-off corner points at the
              speaker's avatar, so the two sides read apart at a glance. */}
          <BubbleContent
            className={
              isUser
                ? "rounded-2xl rounded-br-md px-3.5 py-2.5 shadow-sm"
                : "bg-card! rounded-2xl rounded-bl-md px-3.5 py-2.5 shadow-sm"
            }
          >
            {text}
          </BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  )
}
