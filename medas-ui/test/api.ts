import { vi } from "vitest"

import { auth, currentUser } from "@clerk/nextjs/server"

// Helpers for the api/ specs. Each spec still declares its own
// vi.mock("@clerk/nextjs/server", ...) -- vi.mock is hoisted per file -- and
// these drive that mock.

const TOKEN = "session.jwt.token"

// Signed out is a null token: that is all api/session.ts reads.
const signInAs = (token: string | null = TOKEN) =>
  vi.mocked(auth).mockResolvedValue({
    getToken: async () => token,
  } as unknown as Awaited<ReturnType<typeof auth>>)

// Only the first name is read, so that is all the user needs to carry.
const named = (firstName: string | null) =>
  vi
    .mocked(currentUser)
    .mockResolvedValue({ firstName } as unknown as Awaited<
      ReturnType<typeof currentUser>
    >)

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

// The first request made, with its query read and its body parsed. A GET
// has no body, so that is left undefined rather than parsed.
const requestFrom = (fetchMock: ReturnType<typeof vi.fn>) => {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  const { pathname, searchParams } = new URL(url)

  return {
    url,
    init,
    pathname,
    searchParams,
    body: init.body === undefined ? undefined : JSON.parse(String(init.body)),
  }
}

export { TOKEN, named, requestFrom, signInAs, stubFetch }
