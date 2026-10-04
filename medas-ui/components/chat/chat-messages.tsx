"use client"

import { useEffect, useRef } from "react"

import { ChatMessage } from "@/components/chat/chat-message"
import { TypingIndicator } from "@/components/chat/typing-indicator"
import { ChatMessageProps } from "@/model/ChatMessage"
import { useChatStore } from "@/store/store"

interface ChatMessagesProps {
  // The greeting, fetched on the server before any conversation exists.
  initialMessages: ChatMessageProps[]
}

export function ChatMessages({ initialMessages }: ChatMessagesProps) {
  const messages = useChatStore((s) => s.messages)
  const pending = useChatStore((s) => s.pending)
  const listRef = useRef<HTMLDivElement>(null)

  // The store starts empty, so fall back until the first send fills it. No
  // effect needed to seed it: the create response carries the greeting back
  // alongside the first message, so nothing is lost in the handover. The
  // message in flight goes last; the stored copy replaces it on reply.
  const history = messages.length > 0 ? messages : initialMessages
  const list = pending ? [...history, pending] : history

  // A browser never follows appended content on its own, and the element
  // that scrolls is Radix's Viewport, not the ScrollArea root, so a ref on
  // the root would not help either. Aligning the list's own bottom edge
  // moves whichever ancestor actually scrolls, and keeps the bottom padding
  // in view -- a sentinel inside the flex column would add a stray gap.
  // Keyed on length: a send only ever appends, and the typing indicator
  // comes and goes with pending, which always changes the length too.
  useEffect(() => {
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches
    listRef.current?.scrollIntoView({
      block: "end",
      behavior: reduceMotion ? "auto" : "smooth",
    })
  }, [list.length])

  return (
    // max-w-2xl inside the shell's max-w-3xl: a measure of ~70 characters
    // stays readable, and the narrower column leaves the bubbles room to sit
    // against their own side rather than meeting in the middle.
    <div
      ref={listRef}
      className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-7 sm:px-6 sm:py-9"
    >
      {list.map((message, index) => (
        <ChatMessage
          key={message.message_id ?? `turn-${index}`}
          role={message.role}
          text={message.text}
          severity={message.severity}
          ui={message.ui}
        />
      ))}
      {/* Up for exactly as long as a message is in flight: the reply lands
          in the same store update that clears pending. */}
      {pending ? <TypingIndicator /> : null}
    </div>
  )
}
