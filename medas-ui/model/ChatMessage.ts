export type ChatRole = "user" | "assistant"

// The triage codes the assistant prompt defines. They arrive on assistant
// turns the API answered; the greeting carries none.
export type Severity = "S1" | "S2" | "S3" | "S4" | "S5"

export interface ChatMessageProps {
  role: ChatRole
  text: string
  severity?: Severity
}
