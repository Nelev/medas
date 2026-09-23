import { act, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ChatMessages } from "@/components/chat/chat-messages"
import { useChatStore } from "@/store/store"
import {
  CONVERSATION_ID,
  firstMessage,
  greeting,
  pendingMessage,
  storedReply,
} from "@/test/fixtures"

describe("ChatMessages", () => {
  beforeEach(() => {
    // jsdom implements neither: no layout, so nothing to scroll or query.
    // Assigned rather than spied on, since there is no original to wrap; the
    // matchMedia stub is undone by the afterEach in test/setup.ts.
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: false })),
    )
  })

  it("shows no typing indicator when nothing is in flight", () => {
    render(<ChatMessages initialMessages={[greeting]} />)

    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("shows the pending message after the greeting, then the indicator", () => {
    useChatStore.setState({
      pending: pendingMessage,
    })

    render(<ChatMessages initialMessages={[greeting]} />)

    // The greeting the list falls back to stays in view while it waits.
    expect(screen.getByText(greeting.text)).toBeInTheDocument()
    expect(screen.getByText(firstMessage.text)).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent(
      "Medas is writing a reply",
    )
  })

  it("swaps the indicator for the reply, showing the question once", () => {
    useChatStore.setState({
      pending: pendingMessage,
    })

    render(<ChatMessages initialMessages={[greeting]} />)
    act(() => {
      useChatStore
        .getState()
        .receiveTurns(CONVERSATION_ID, [greeting, firstMessage, storedReply])
    })

    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    expect(screen.getAllByText(firstMessage.text)).toHaveLength(1)
    expect(screen.getByText(storedReply.text)).toBeInTheDocument()
  })

  it("scrolls to the bottom when the indicator comes in", () => {
    render(<ChatMessages initialMessages={[greeting]} />)
    vi.mocked(Element.prototype.scrollIntoView).mockClear()

    act(() => {
      useChatStore.setState({
        pending: pendingMessage,
      })
    })

    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ block: "end" }),
    )
  })
})
