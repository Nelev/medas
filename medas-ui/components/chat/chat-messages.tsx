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
    <div className="flex flex-col gap-4 px-4 py-6 sm:gap-6 sm:px-6">
      {list.map((message, index) => (
        <ChatMessage key={index} role={message.role} text={message.text} />
      ))}
    </div>
  )
}
