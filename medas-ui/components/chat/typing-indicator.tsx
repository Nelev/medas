import { MessageRow } from "@/components/chat/chat-message"

// Where the assistant's reply is about to land, drawn in the row that reply
// will use, so the answer takes its place rather than appearing somewhere new.
export function TypingIndicator() {
  return (
    // role="status" so a screen reader hears that an answer is coming; the
    // dots alone say nothing to it.
    <MessageRow speaker="assistant" role="status">
      {/* One line of text tall, so the bubble does not change height when
          the reply replaces it. */}
      <span className="flex h-[1.625em] items-center gap-1" aria-hidden>
        {/* Staggered, so the rise travels left to right. */}
        {[0, 0.16, 0.32].map((delay) => (
          <span
            key={delay}
            className="typing-dot bg-primary size-1.5 rounded-full opacity-35"
            style={{ animationDelay: `${delay}s` }}
          />
        ))}
      </span>
      <span className="sr-only">Medas is writing a reply</span>
    </MessageRow>
  )
}
