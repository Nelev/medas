export type ChatRole = "user" | "assistant"

// The triage codes the assistant prompt defines. They arrive on assistant
// turns the API answered; the greeting carries none.
export type Severity = "S1" | "S2" | "S3" | "S4" | "S5"

export interface ChatMessageProps {
  // Minted by the API; absent on the greeting and on a message not yet sent.
  message_id?: string
  role: ChatRole
  text: string
  severity?: Severity
  // A json-render spec the assistant may attach; unvalidated until drawn.
  ui?: unknown
}
