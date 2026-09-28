import { beforeEach, describe, expect, it, vi } from "vitest"

import { ask, getConversation } from "@/api/chat"
import { requestFrom, signInAs, stubFetch, TOKEN } from "@/test/api"
import {
  askedTurns,
  CONVERSATION_ID,
  createdConversation,
  jsonResponse,
  storedMessage,
  storedReply,
} from "@/test/fixtures"

// The session is Clerk's to read, so it is mocked; each test starts signed in.
vi.mock("@clerk/nextjs/server", () => ({ auth: vi.fn() }))

beforeEach(() => {
  signInAs()
})

describe("ask", () => {
  it("posts to /ask with the session token and the conversation", async () => {
    const fetchMock = stubFetch(jsonResponse(askedTurns, 201))

    await ask({ role: "user", text: "And my medications?" }, CONVERSATION_ID)

    const { url, init } = requestFrom(fetchMock)
    const { searchParams, pathname } = new URL(url)

    expect(pathname).toBe("/ask")
    expect(searchParams.get("conversationId")).toBe(CONVERSATION_ID)
    expect(init.method).toBe("POST")
    expect(init.headers).toMatchObject({
      "Content-Type": "application/json",
      Authorization: `Bearer ${TOKEN}`,
    })
  })

  it("omits the conversation when there is not one yet", async () => {
    // Absent, not empty: the API starts a conversation when the parameter is
    // missing, and an empty one would be a 422 rather than a new thread.
    const fetchMock = stubFetch(jsonResponse(createdConversation, 201))

    await ask({ role: "user", text: "Do I have any allergies?" })

    const { searchParams } = new URL(requestFrom(fetchMock).url)

    expect(searchParams.has("conversationId")).toBe(false)
    // Who is asking is the token's to say, never the URL's.
    expect(searchParams.has("userId")).toBe(false)
  })

  it("returns the whole opening when it started the conversation", async () => {
    stubFetch(jsonResponse(createdConversation, 201))

    const { conversationId, turns } = await ask({ role: "user", text: "hi" })

    expect(conversationId).toBe(CONVERSATION_ID)
    // The greeting the API seeded, and the question.
    expect(turns.map((turn) => turn.role)).toEqual(["assistant", "user"])
  })

  it("sends the message flat rather than wrapped", async () => {
    const fetchMock = stubFetch(jsonResponse(askedTurns, 201))

    await ask({ role: "user", text: "And my medications?" }, CONVERSATION_ID)

    expect(requestFrom(fetchMock).body).toEqual({
      role: "user",
      text: "And my medications?",
    })
  })

  it("returns the stored turn and the agent's reply to it", async () => {
    stubFetch(jsonResponse(askedTurns, 201))

    const { turns } = await ask({ role: "user", text: "x" }, CONVERSATION_ID)

    expect(turns).toEqual([storedMessage, storedReply])
    expect(turns[0].message_id).toBeTruthy()
    expect(turns[0].timestamp).toBeTruthy()
  })

  it("rejects when the conversation is unknown or soft-deleted", async () => {
    stubFetch(jsonResponse({ detail: "Conversation not found" }, 404))

    await expect(
      ask({ role: "user", text: "x" }, CONVERSATION_ID),
    ).rejects.toThrow("404")
  })

  it("refuses to ask without a session, before calling the API", async () => {
    signInAs(null)
    const fetchMock = stubFetch(jsonResponse(askedTurns, 201))

    await expect(
      ask({ role: "user", text: "x" }, CONVERSATION_ID),
    ).rejects.toThrow("Not signed in")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("propagates a network failure instead of resolving undefined", async () => {
    // What a CORS rejection or a dead API looks like to the caller: fetch
    // rejects outright, there is no response to inspect.
    stubFetch(Promise.reject(new TypeError("Failed to fetch")))

    await expect(
      ask({ role: "user", text: "x" }, CONVERSATION_ID),
    ).rejects.toThrow("Failed to fetch")
  })
})

describe("getConversation", () => {
  it("reads the whole conversation with a GET, the session token alone", async () => {
    const fetchMock = stubFetch(jsonResponse(createdConversation))

    const result = await getConversation(CONVERSATION_ID)

    const { pathname, init } = requestFrom(fetchMock)
    expect(pathname).toBe(`/conversations/${CONVERSATION_ID}`)
    expect(init.method).toBe("GET")
    expect(init.headers).toMatchObject({ Authorization: `Bearer ${TOKEN}` })
    expect(result).toEqual({
      conversationId: CONVERSATION_ID,
      turns: createdConversation.messages,
    })
  })

  it("throws when the conversation is not the user's", async () => {
    stubFetch(jsonResponse({ detail: "Conversation not found" }, 404))

    await expect(getConversation(CONVERSATION_ID)).rejects.toThrow("404")
  })
})
