import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { postMessage, startNewConversation } from "@/api/chat"
import { ChatComposer } from "@/components/chat/chat-composer"
import { useChatStore } from "@/store/store"
import {
  CONVERSATION_ID,
  createdConversation,
  firstMessage,
  greeting,
  storedMessage,
} from "@/test/fixtures"

// The API client is mocked here, not fetch: its own contract with the server
// is covered in api/chat.test.ts, and what matters at this level is which of
// the two calls the composer chooses and what it does with the answer.
vi.mock("@/api/chat", () => ({
  startNewConversation: vi.fn(),
  postMessage: vi.fn(),
}))

const mockedStart = vi.mocked(startNewConversation)
const mockedPost = vi.mocked(postMessage)

/**
 * Swallows the promise rejections that escape the composer while a test is
 * running, and restores normal reporting afterwards.
 *
 * Only for the failure tests below: handleSubmit has no catch, so a rejected
 * send becomes an unhandled rejection that fails the whole run. Scoped to the
 * tests that provoke it rather than switched off globally, so a rejection
 * anywhere else still fails the suite the way it should.
 */
const swallowUnhandledRejections = () => {
  const suppress = (event: PromiseRejectionEvent) => event.preventDefault()

  window.addEventListener("unhandledrejection", suppress)
  process.on("unhandledRejection", () => {})

  return () => {
    window.removeEventListener("unhandledrejection", suppress)
    process.removeAllListeners("unhandledRejection")
  }
}

const send = async (text: string) => {
  const user = userEvent.setup()

  await user.type(screen.getByRole("textbox", { name: "Message" }), text)
  await user.click(screen.getByRole("button", { name: "Send message" }))
}

describe("ChatComposer", () => {
  beforeEach(() => {
    mockedStart.mockReset()
    mockedPost.mockReset()
    mockedStart.mockResolvedValue({
      conversationId: CONVERSATION_ID,
      messages: createdConversation.messages,
    })
    mockedPost.mockResolvedValue(storedMessage)
  })

  describe("with no conversation yet", () => {
    it("creates one rather than appending", async () => {
      render(<ChatComposer />)

      await send("Do I have any allergies?")

      await waitFor(() => expect(mockedStart).toHaveBeenCalledTimes(1))
      expect(mockedStart).toHaveBeenCalledWith({
        role: "user",
        text: "Do I have any allergies?",
      })
      // Appending to a conversation that does not exist is a 404, so this
      // must not fire on the first message.
      expect(mockedPost).not.toHaveBeenCalled()
    })

    it("keeps the id so the next message can append", async () => {
      render(<ChatComposer />)

      await send("hello")

      await waitFor(() =>
        expect(useChatStore.getState().conversationId).toBe(CONVERSATION_ID),
      )
    })

    it("replaces the list with everything the server seeded", async () => {
      // Seeded with a leftover message so replace and append are actually
      // distinguishable. With an empty store the two are identical, and the
      // assertion would hold either way -- which is no assertion at all.
      useChatStore.setState({ messages: [{ role: "user", text: "stale" }] })

      render(<ChatComposer />)

      await send("hello")

      // Both messages, greeting first, and nothing else: the API seeds the
      // greeting alongside the user's own, so its reply is the whole history.
      // Appending would leave the stale entry and show the greeting twice.
      await waitFor(() =>
        expect(useChatStore.getState().messages).toEqual([greeting, firstMessage]),
      )
    })
  })

  describe("with a conversation in hand", () => {
    beforeEach(() => {
      useChatStore.setState({
        conversationId: CONVERSATION_ID,
        messages: [greeting, firstMessage],
      })
    })

    it("appends to that conversation", async () => {
      render(<ChatComposer />)

      await send("And my medications?")

      await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
      expect(mockedPost).toHaveBeenCalledWith(
        { role: "user", text: "And my medications?" },
        CONVERSATION_ID,
      )
      // A second create would strand the first conversation and start a new
      // one behind the user's back.
      expect(mockedStart).not.toHaveBeenCalled()
    })

    it("keeps the history and puts the new message last", async () => {
      render(<ChatComposer />)

      await send("And my medications?")

      await waitFor(() =>
        expect(useChatStore.getState().messages).toEqual([
          greeting,
          firstMessage,
          storedMessage,
        ]),
      )
    })
  })

  describe("input handling", () => {
    it("sends nothing when the field is empty", async () => {
      const user = userEvent.setup()

      render(<ChatComposer />)
      await user.click(screen.getByRole("button", { name: "Send message" }))

      expect(mockedStart).not.toHaveBeenCalled()
      expect(mockedPost).not.toHaveBeenCalled()
      expect(useChatStore.getState().messages).toEqual([])
    })

    it("sends nothing when the field holds only whitespace", async () => {
      render(<ChatComposer />)

      await send("   ")

      expect(mockedStart).not.toHaveBeenCalled()
      expect(mockedPost).not.toHaveBeenCalled()
    })

    it("trims what it does send", async () => {
      render(<ChatComposer />)

      await send("  Do I have any allergies?  ")

      await waitFor(() =>
        expect(mockedStart).toHaveBeenCalledWith({
          role: "user",
          text: "Do I have any allergies?",
        }),
      )
    })

    it("clears the field after sending", async () => {
      render(<ChatComposer />)

      await send("hello")

      await waitFor(() =>
        expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue(""),
      )
    })
  })

  describe("when the send fails", () => {
    it("leaves the history untouched", async () => {
      const restore = swallowUnhandledRejections()

      mockedStart.mockRejectedValue(new Error("Failed to fetch"))

      render(<ChatComposer />)
      await send("hello")

      await waitFor(() => expect(mockedStart).toHaveBeenCalled())
      expect(useChatStore.getState().messages).toEqual([])
      expect(useChatStore.getState().conversationId).toBe("")

      restore()
    })

    it("does not tell the user anything went wrong", async () => {
      // Pinning a gap, not endorsing it: the failure is silent. The field is
      // already cleared, so the message is simply gone with no explanation.
      // Delete this test when the handler learns to surface an error.
      const restore = swallowUnhandledRejections()

      mockedStart.mockRejectedValue(new Error("Failed to fetch"))

      render(<ChatComposer />)
      await send("hello")

      await waitFor(() => expect(mockedStart).toHaveBeenCalled())
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
      expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("")

      restore()
    })
  })
})
