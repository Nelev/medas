import { beforeEach, describe, expect, it, vi } from "vitest"

import { init } from "@/api/init"
import { requestFrom, signInAs, stubFetch, TOKEN } from "@/test/api"
import {
  conversationList,
  greeting,
  initResponse,
  jsonResponse,
} from "@/test/fixtures"

// The session is Clerk's to read, so it is mocked; each test starts signed in.
vi.mock("@clerk/nextjs/server", () => ({ auth: vi.fn() }))

beforeEach(() => {
  signInAs()
})

describe("init", () => {
  it("asks for the greeting with the session token alone", async () => {
    const fetchMock = stubFetch(jsonResponse(initResponse))

    const { messages } = await init()

    const { pathname, init: request } = requestFrom(fetchMock)

    expect(pathname).toBe("/")
    expect(request.headers).toMatchObject({ Authorization: `Bearer ${TOKEN}` })
    expect(messages).toEqual([greeting])
  })

  it("maps the past conversations to camelCase, newest first", async () => {
    stubFetch(jsonResponse(initResponse))

    const { conversations } = await init()

    expect(conversations).toEqual(conversationList)
  })

  it("throws when the API refuses", async () => {
    stubFetch(jsonResponse({ detail: "Unauthorized" }, 401))

    await expect(init()).rejects.toThrow("401")
  })
})
