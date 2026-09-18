import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterEach, beforeEach, vi } from "vitest"

import { useChatStore } from "@/store/store"

beforeEach(() => {
  // The zustand store is a module singleton, so state survives between tests
  // and whichever ran first would silently decide the result of the next.
  useChatStore.setState({ conversationId: "", messages: [] })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
