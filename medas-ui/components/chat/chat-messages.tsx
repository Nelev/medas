"use client"

import { ChatMessage } from "@/components/chat/chat-message"
import { ChatMessageProps } from "@/model/ChatMessage"
import { useChatStore } from "@/store/store"

interface ChatMessagesProps {
  // The greeting, fetched on the server before any conversation exists.
  initialMessages: ChatMessageProps[]
}

export function ChatMessages({ initialMessages }: ChatMessagesProps) {
  const messages = useChatStore((s) => s.messages)

  // The store starts empty, so fall back until the first send fills it. No
  // effect needed to seed it: the create response carries the greeting back
  // alongside the first message, so nothing is lost in the handover.
  const list = messages.length > 0 ? messages : initialMessages

  return (
    // max-w-2xl inside the shell's max-w-3xl: a measure of ~70 characters
    // stays readable, and the narrower column leaves the bubbles room to sit
    // against their own side rather than meeting in the middle.
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8">
      {list.map((message, index) => (
        <ChatMessage key={index} role={message.role} text={message.text} />
      ))}
    </div>
  )
}
