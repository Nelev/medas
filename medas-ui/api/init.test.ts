import { beforeEach, describe, expect, it, vi } from "vitest"

import { init } from "@/api/init"
import { requestFrom, signInAs, stubFetch, TOKEN } from "@/test/api"
import { greeting, jsonResponse } from "@/test/fixtures"

// The session is Clerk's to read, so it is mocked; each test starts signed in.
vi.mock("@clerk/nextjs/server", () => ({ auth: vi.fn() }))

beforeEach(() => {
  signInAs()
})

describe("init", () => {
  it("asks for a greeting addressed to the given name", async () => {
    const fetchMock = stubFetch(jsonResponse({ messages: [greeting] }))

    const { messages } = await init("Ada Lovelace")

    const { pathname, searchParams, init: request } = requestFrom(fetchMock)

    expect(pathname).toBe("/")
    expect(searchParams.get("user")).toBe("Ada Lovelace")
    expect(request.headers).toMatchObject({ Authorization: `Bearer ${TOKEN}` })
    expect(messages).toEqual([greeting])
  })

  it("leaves the name to the API when there is none", async () => {
    const fetchMock = stubFetch(jsonResponse({ messages: [greeting] }))

    await init()

    expect(requestFrom(fetchMock).searchParams.has("user")).toBe(false)
  })

  it("throws when the API refuses", async () => {
    stubFetch(jsonResponse({ detail: "Unauthorized" }, 401))

    await expect(init("Ada")).rejects.toThrow("401")
  })
})
