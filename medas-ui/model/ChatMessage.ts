export type ChatRole = "user" | "assistant"

export interface ChatMessageProps {
  role: ChatRole
  text: string
}
