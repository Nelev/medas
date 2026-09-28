import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ask, uploadPdf } from "@/api/chat"
import { ChatComposer } from "@/components/chat/chat-composer"
import { useChatStore } from "@/store/store"
import {
  CONVERSATION_ID,
  createdConversation,
  firstMessage,
  greeting,
  pendingMessage,
  storedMessage,
  storedReply,
} from "@/test/fixtures"

// The API client is mocked here, not fetch: its own contract with the server
// is covered in api/chat.test.ts, and what matters at this level is what the
// composer passes it and what it does with the answer.
vi.mock("@/api/chat", () => ({
  ask: vi.fn(),
  uploadPdf: vi.fn(),
}))

// The snackbar is the library's to draw; what matters here is what the
// composer asks it to say.
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const mockedAsk = vi.mocked(ask)
const mockedUploadPdf = vi.mocked(uploadPdf)

const send = async (text: string) => {
  const user = userEvent.setup()
  const field = screen.getByRole("textbox", { name: "Message" })

  // Cleared first so a second send in the same test starts from an empty
  // field rather than appending to whatever is already there.
  await user.clear(field)
  await user.type(field, text)
  await user.click(screen.getByRole("button", { name: "Send message" }))
}

// A request that settles only when the test says so, to hold the composer in
// the window between sending and the answer.
const hold = <T,>(mock: {
  mockReturnValue: (value: Promise<T>) => unknown
}) => {
  let settle!: { resolve: (value: T) => void; reject: (cause: Error) => void }
  mock.mockReturnValue(
    new Promise<T>((resolve, reject) => {
      settle = { resolve, reject }
    }),
  )
  return settle
}

describe("ChatComposer", () => {
  beforeEach(() => {
    mockedAsk.mockReset()
    // What a follow-up answers with: the message and the agent's reply.
    mockedAsk.mockResolvedValue({
      conversationId: CONVERSATION_ID,
      turns: [storedMessage, storedReply],
    })
  })

  describe("with no conversation yet", () => {
    it("sends without an id, so the API starts one", async () => {
      render(<ChatComposer />)

      await send("Do I have any allergies?")

      await waitFor(() => expect(mockedAsk).toHaveBeenCalledTimes(1))
      // An empty id, which the client omits from the query -- naming a
      // conversation that does not exist would be a 404 rather than a new
      // thread.
      expect(mockedAsk).toHaveBeenCalledWith(
        { role: "user", text: "Do I have any allergies?" },
        "",
      )
    })

    it("keeps the id so the next message can append", async () => {
      render(<ChatComposer />)

      await send("hello")

      await waitFor(() =>
        expect(useChatStore.getState().conversationId).toBe(CONVERSATION_ID),
      )
    })

    it("shows the greeting the server seeded, once", async () => {
      // The store is empty before the first send, so appending the turns the
      // API returns is the same as replacing -- and the greeting the server
      // seeded is the only one rendered. The preview greeting lives in
      // ChatMessages' initialMessages, which it stops using the moment the
      // store has anything in it.
      mockedAsk.mockResolvedValue({
        conversationId: CONVERSATION_ID,
        turns: createdConversation.messages,
      })

      render(<ChatComposer />)

      await send("hello")

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

      await waitFor(() => expect(mockedAsk).toHaveBeenCalledTimes(1))
      // The id it holds, so the API appends rather than starting a thread.
      expect(mockedAsk).toHaveBeenCalledWith(
        { role: "user", text: "And my medications?" },
        CONVERSATION_ID,
      )
    })

    it("keeps the history and puts the new turns last, in order", async () => {
      render(<ChatComposer />)

      await send("And my medications?")

      await waitFor(() =>
        expect(useChatStore.getState().messages).toEqual([
          greeting,
          firstMessage,
          // The question, then the answer to it -- never the other way round.
          storedMessage,
          storedReply,
        ]),
      )
    })
  })

  describe("while the reply is on its way", () => {
    it("shows the message before the API answers", async () => {
      hold(mockedAsk)

      render(<ChatComposer />)
      await send("Do I have any allergies?")

      expect(useChatStore.getState().pending).toEqual(pendingMessage)
      // Held apart, so the greeting the list falls back to stays in view.
      expect(useChatStore.getState().messages).toEqual([])
    })

    it("hands over to the stored copy once the reply lands", async () => {
      const settle = hold(mockedAsk)

      render(<ChatComposer />)
      await send("Do I have any allergies?")
      settle.resolve({
        conversationId: CONVERSATION_ID,
        turns: createdConversation.messages,
      })

      await waitFor(() => expect(useChatStore.getState().pending).toBeNull())
      // Once, as stored -- not the optimistic copy as well.
      expect(useChatStore.getState().messages).toEqual([greeting, firstMessage])
    })

    it("takes the message back out when the send fails", async () => {
      const settle = hold(mockedAsk)

      render(<ChatComposer />)
      await send("hello")
      settle.reject(new Error("Failed to fetch"))

      await screen.findByRole("alert")
      expect(useChatStore.getState().pending).toBeNull()
      expect(useChatStore.getState().messages).toEqual([])
    })

    it("does not send a second message until the first is answered", async () => {
      hold(mockedAsk)

      render(<ChatComposer />)
      await send("hello")

      expect(
        screen.getByRole("button", { name: "Send message" }),
      ).toBeDisabled()
      // Enter submits the form without going through the button.
      await userEvent.type(
        screen.getByRole("textbox", { name: "Message" }),
        "again{Enter}",
      )
      expect(mockedAsk).toHaveBeenCalledTimes(1)
    })

    it("appends to the list as it stands when the reply lands", async () => {
      // A list captured at submit would drop anything written meanwhile.
      const settle = hold(mockedAsk)

      render(<ChatComposer />)
      await send("And my medications?")
      useChatStore.setState({ messages: [greeting, firstMessage] })
      settle.resolve({
        conversationId: CONVERSATION_ID,
        turns: [storedMessage, storedReply],
      })

      await waitFor(() =>
        expect(useChatStore.getState().messages).toEqual([
          greeting,
          firstMessage,
          storedMessage,
          storedReply,
        ]),
      )
    })
  })

  describe("input handling", () => {
    it("sends nothing when the field is empty", async () => {
      const user = userEvent.setup()

      render(<ChatComposer />)
      await user.click(screen.getByRole("button", { name: "Send message" }))

      expect(mockedAsk).not.toHaveBeenCalled()
      expect(useChatStore.getState().messages).toEqual([])
    })

    it("sends nothing when the field holds only whitespace", async () => {
      render(<ChatComposer />)

      await send("   ")

      expect(mockedAsk).not.toHaveBeenCalled()
    })

    it("trims what it does send", async () => {
      render(<ChatComposer />)

      await send("  Do I have any allergies?  ")

      await waitFor(() =>
        expect(mockedAsk).toHaveBeenCalledWith(
          { role: "user", text: "Do I have any allergies?" },
          "",
        ),
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
      mockedAsk.mockRejectedValue(new Error("Failed to fetch"))

      render(<ChatComposer />)
      await send("hello")

      await waitFor(() => expect(mockedAsk).toHaveBeenCalled())
      // Nothing was stored, so nothing may appear in the list.
      expect(useChatStore.getState().messages).toEqual([])
      expect(useChatStore.getState().conversationId).toBe("")
    })

    it("tells the user, quoting what went wrong", async () => {
      mockedAsk.mockRejectedValue(new Error("Failed to fetch"))

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
      mockedAsk.mockRejectedValue(new Error("Failed to fetch"))

      render(<ChatComposer />)
      await send("hello")

      await screen.findByRole("alert")
      expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("")
    })

    it("clears the warning once a send succeeds", async () => {
      mockedAsk.mockRejectedValueOnce(new Error("Failed to fetch"))

      render(<ChatComposer />)
      await send("hello")
      await screen.findByRole("alert")

      mockedAsk.mockResolvedValue({
        conversationId: CONVERSATION_ID,
        turns: createdConversation.messages,
      })
      await send("again")

      await waitFor(() =>
        expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
      )
    })
  })

  describe("uploading a PDF", () => {
    const pdf = new File(["%PDF-1.4"], "record.pdf", {
      type: "application/pdf",
    })

    // Same envelope as ask: the request turn and the agent's answer.
    const uploaded = {
      conversationId: CONVERSATION_ID,
      turns: [storedMessage, storedReply],
    }

    beforeEach(() => {
      mockedUploadPdf.mockReset()
    })

    it("sends the picked file, without an id before the first send", async () => {
      mockedUploadPdf.mockResolvedValue(uploaded)
      render(<ChatComposer />)

      await userEvent.upload(screen.getByLabelText("PDF file"), pdf)

      await waitFor(() => expect(mockedUploadPdf).toHaveBeenCalledTimes(1))
      const [formData, conversationId] = mockedUploadPdf.mock.calls[0]
      expect(formData.get("file")).toBe(pdf)
      expect(conversationId).toBe("")
    })

    it("names the conversation and appends the turns it added", async () => {
      mockedUploadPdf.mockResolvedValue(uploaded)
      useChatStore.setState({ conversationId: CONVERSATION_ID })
      render(<ChatComposer />)

      await userEvent.upload(screen.getByLabelText("PDF file"), pdf)

      await waitFor(() =>
        expect(useChatStore.getState().messages).toEqual(uploaded.turns),
      )
      expect(mockedUploadPdf.mock.calls[0][1]).toBe(CONVERSATION_ID)
    })

    it("shows the failure", async () => {
      mockedUploadPdf.mockRejectedValue(new Error("Failed to fetch"))
      render(<ChatComposer />)

      await userEvent.upload(screen.getByLabelText("PDF file"), pdf)

      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith(
          expect.stringContaining("Your PDF was not uploaded"),
        ),
      )
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    })

    it("shows the upload in progress until it lands", async () => {
      const settle = hold(mockedUploadPdf)
      render(<ChatComposer />)

      await userEvent.upload(screen.getByLabelText("PDF file"), pdf)

      expect(
        await screen.findByRole("button", { name: "Uploading document..." }),
      ).toBeDisabled()

      settle.resolve(uploaded)

      expect(
        await screen.findByRole("button", { name: "Upload document" }),
      ).toBeEnabled()
    })

    it("holds the send until the upload lands", async () => {
      const settle = hold(mockedUploadPdf)
      render(<ChatComposer />)

      await userEvent.upload(screen.getByLabelText("PDF file"), pdf)

      // Before the first message, a send now would start a second
      // conversation alongside the one the upload is starting.
      expect(
        await screen.findByRole("button", { name: "Send message" }),
      ).toBeDisabled()
      await userEvent.type(
        screen.getByRole("textbox", { name: "Message" }),
        "Do I have any allergies?{Enter}",
      )
      expect(mockedAsk).not.toHaveBeenCalled()

      settle.resolve(uploaded)

      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: "Send message" }),
        ).toBeEnabled(),
      )
    })

    it("leaves the upload button usable after a failure", async () => {
      mockedUploadPdf.mockRejectedValue(new Error("Failed to fetch"))
      render(<ChatComposer />)

      await userEvent.upload(screen.getByLabelText("PDF file"), pdf)

      await waitFor(() => expect(toast.error).toHaveBeenCalled())
      expect(
        screen.getByRole("button", { name: "Upload document" }),
      ).toBeEnabled()
    })
  })
})
