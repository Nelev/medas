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

const send = async (text: string) => {
  const user = userEvent.setup()
  const field = screen.getByRole("textbox", { name: "Message" })

  // Cleared first so a second send in the same test starts from an empty
  // field rather than appending to whatever is already there.
  await user.clear(field)
  await user.type(field, text)
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
        expect(useChatStore.getState().messages).toEqual([
          greeting,
          firstMessage,
        ]),
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
        expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue(
          "",
        ),
      )
    })
  })

  describe("when the send fails", () => {
    it("leaves the history untouched", async () => {
      mockedStart.mockRejectedValue(new Error("Failed to fetch"))

      render(<ChatComposer />)
      await send("hello")

      await waitFor(() => expect(mockedStart).toHaveBeenCalled())
      // Nothing was stored, so nothing may appear in the list.
      expect(useChatStore.getState().messages).toEqual([])
      expect(useChatStore.getState().conversationId).toBe("")
    })

    it("tells the user, quoting what went wrong", async () => {
      mockedStart.mockRejectedValue(new Error("Failed to fetch"))

      render(<ChatComposer />)
      await send("hello")

      const alert = await screen.findByRole("alert")

      expect(alert).toHaveTextContent("Failed to fetch")
      expect(alert).toHaveTextContent("Your message was not sent")
    })

    it("does not keep the text that failed to send", async () => {
      // Pinning the trade-off, not endorsing it: the field is cleared
      // optimistically on submit and stays cleared on failure, so retrying
      // means retyping. Flip this test if the draft is ever restored.
      mockedStart.mockRejectedValue(new Error("Failed to fetch"))

      render(<ChatComposer />)
      await send("hello")

      await screen.findByRole("alert")
      expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("")
    })

    it("clears the warning once a send succeeds", async () => {
      mockedStart.mockRejectedValueOnce(new Error("Failed to fetch"))

      render(<ChatComposer />)
      await send("hello")
      await screen.findByRole("alert")

      mockedStart.mockResolvedValue({
        conversationId: CONVERSATION_ID,
        messages: createdConversation.messages,
      })
      await send("again")

      await waitFor(() =>
        expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
      )
    })
  })
})
