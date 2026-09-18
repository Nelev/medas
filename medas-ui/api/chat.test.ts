import { beforeEach, describe, expect, it, vi } from "vitest"

import { postMessage, startNewConversation } from "@/api/chat"
import {
  CONVERSATION_ID,
  createdConversation,
  jsonResponse,
  storedMessage,
  USER_ID,
} from "@/test/fixtures"

// globalThis.fetch is stubbed rather than the module mocked: the URL building
// and the response mapping are the things under test, and mocking the module
// would skip both.
const stubFetch = (response: Response | Promise<never>) => {
  const fetchMock = vi.fn(() =>
    response instanceof Promise ? response : Promise.resolve(response),
  )

  vi.stubGlobal("fetch", fetchMock)

  return fetchMock
}

const requestFrom = (fetchMock: ReturnType<typeof vi.fn>) => {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]

  return { url, init, body: JSON.parse(String(init.body)) }
}

describe("startNewConversation", () => {
  beforeEach(() => {
    stubFetch(jsonResponse(createdConversation, 201))
  })

  it("posts to /conversations with the owner as a query parameter", async () => {
    const fetchMock = stubFetch(jsonResponse(createdConversation, 201))

    await startNewConversation({ role: "user", text: "Do I have any allergies?" })

    const { url, init } = requestFrom(fetchMock)

    expect(url).toBe(`http://localhost:8000/conversations?userId=${USER_ID}`)
    expect(init.method).toBe("POST")
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" })
  })

  it("sends the message flat rather than wrapped", async () => {
    const fetchMock = stubFetch(jsonResponse(createdConversation, 201))

    await startNewConversation({ role: "user", text: "Do I have any allergies?" })

    // The API expects NewMessage at the top level. A { message: ... } wrapper
    // is a 422, which is how this was written before.
    expect(requestFrom(fetchMock).body).toEqual({
      role: "user",
      text: "Do I have any allergies?",
    })
  })

  it("maps the snake_case id the API returns to camelCase", async () => {
    stubFetch(jsonResponse(createdConversation, 201))

    const created = await startNewConversation({ role: "user", text: "hi" })

    expect(created.conversationId).toBe(CONVERSATION_ID)
    // The property the API actually sends must not leak past this boundary.
    expect(created).not.toHaveProperty("conversation_id")
  })

  it("returns every seeded message, not just the one that was sent", async () => {
    stubFetch(jsonResponse(createdConversation, 201))

    const created = await startNewConversation({ role: "user", text: "hi" })

    // The API seeds the greeting alongside the first message, so the reply is
    // the whole history. A caller that appends this instead of replacing ends
    // up showing the greeting twice.
    expect(created.messages).toHaveLength(2)
    expect(created.messages.map((message) => message.role)).toEqual([
      "assistant",
      "user",
    ])
  })

  it("rejects when the user is unknown", async () => {
    stubFetch(jsonResponse({ detail: "User not found" }, 404))

    await expect(
      startNewConversation({ role: "user", text: "hi" }),
    ).rejects.toThrow("404")
  })
})

describe("postMessage", () => {
  it("posts to the conversation's own messages path", async () => {
    const fetchMock = stubFetch(jsonResponse(storedMessage, 201))

    await postMessage({ role: "user", text: "And my medications?" }, CONVERSATION_ID)

    const { url } = requestFrom(fetchMock)

    expect(url).toBe(
      `http://localhost:8000/conversations/${CONVERSATION_ID}/messages`,
    )
    // A doubled slash resolves to a different path on some servers and is
    // exactly the typo this file shipped with once.
    expect(url).not.toContain("//conversations")
  })

  it("sends the message flat rather than wrapped", async () => {
    const fetchMock = stubFetch(jsonResponse(storedMessage, 201))

    await postMessage({ role: "user", text: "And my medications?" }, CONVERSATION_ID)

    expect(requestFrom(fetchMock).body).toEqual({
      role: "user",
      text: "And my medications?",
    })
  })

  it("returns the stored message with the fields the server minted", async () => {
    stubFetch(jsonResponse(storedMessage, 201))

    const stored = await postMessage({ role: "user", text: "x" }, CONVERSATION_ID)

    expect(stored).toEqual(storedMessage)
    expect(stored.message_id).toBeTruthy()
    expect(stored.timestamp).toBeTruthy()
  })

  it("rejects when the conversation is unknown or soft-deleted", async () => {
    stubFetch(jsonResponse({ detail: "Conversation not found" }, 404))

    await expect(
      postMessage({ role: "user", text: "x" }, CONVERSATION_ID),
    ).rejects.toThrow("404")
  })

  it("propagates a network failure instead of resolving undefined", async () => {
    // What a CORS rejection or a dead API looks like to the caller: fetch
    // rejects outright, there is no response to inspect.
    stubFetch(Promise.reject(new TypeError("Failed to fetch")))

    await expect(
      postMessage({ role: "user", text: "x" }, CONVERSATION_ID),
    ).rejects.toThrow("Failed to fetch")
  })
})
