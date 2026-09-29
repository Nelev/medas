import { Stethoscope, User } from "lucide-react"
import type { ComponentProps, ReactNode } from "react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import { Message, MessageAvatar, MessageContent } from "@/components/ui/message"
import { ReplyUI } from "@/components/chat/reply-ui"
import { ChatMessageProps, ChatRole, Severity } from "@/model/ChatMessage"

// Straight from the prompt's table, shortened to fit a chip. The code is
// shown alongside, so the word is a gloss rather than the only signal.
const SEVERITY_LABEL: Record<Severity, string> = {
  S1: "emergency",
  S2: "urgent",
  S3: "routine",
  S4: "self-care",
  S5: "informational",
}

export function ChatMessage({ role, text, severity, ui }: ChatMessageProps) {
  // The one case the accent colour is spent on: an answer that says go now.
  const isUrgent = severity === "S1"

  return (
    <MessageRow
      speaker={role}
      isUrgent={isUrgent}
      footer={
        severity ? (
          // Stored with the turn and returned in the payload since the API
          // started triaging; this is where it finally shows.
          <span
            className={`mt-1.5 inline-flex w-fit items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[0.6875rem] tracking-[0.04em] uppercase ${
              isUrgent
                ? "border-pulse/45 text-pulse"
                : "border-primary/30 text-primary"
            }`}
          >
            <span
              className={`size-1.5 rounded-full ${isUrgent ? "bg-pulse" : "bg-primary"}`}
              aria-hidden
            />
            {severity} {SEVERITY_LABEL[severity]}
          </span>
        ) : null
      }
    >
      {ui ? <ReplyUI spec={ui} fallback={text} /> : text}
    </MessageRow>
  )
}

interface MessageRowProps extends Omit<
  ComponentProps<typeof BubbleContent>,
  "className"
> {
  // Not `role`: that name belongs to the bubble's ARIA role, passed through.
  speaker: ChatRole
  isUrgent?: boolean
  // Under the bubble, inside the same column -- the severity chip.
  footer?: ReactNode
}

// The row every turn is drawn in, exported so a placeholder for a turn (the
// typing indicator) is the same row the turn will replace it with.
export function MessageRow({
  speaker,
  isUrgent = false,
  footer,
  ...contentProps
}: MessageRowProps) {
  const isUser = speaker === "user"
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
                ? "bg-muted text-muted-foreground"
                : "bg-primary/12 text-primary"
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
              speaker's avatar, so the two sides read apart at a glance. The
              assistant sits on the sage wash with a rule down its left edge --
              a margin mark, the way an annotated chart is marked. */}
          <BubbleContent
            {...contentProps}
            className={
              isUser
                ? "bg-primary! shadow-primary/25 rounded-2xl rounded-br-md px-4 py-2.5 shadow-md"
                : isUrgent
                  ? "bg-pulse/7! border-pulse/25 border-l-pulse rounded-2xl rounded-bl-md border border-l-2 px-4 py-2.5"
                  : "bg-secondary! border-primary/15 border-l-primary/55 rounded-2xl rounded-bl-md border border-l-2 px-4 py-2.5"
            }
          />
        </Bubble>

        {footer}
      </MessageContent>
    </Message>
  )
}
