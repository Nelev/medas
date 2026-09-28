import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterEach, beforeEach, vi } from "vitest"

import { useChatStore } from "@/store/store"

// jsdom has no ResizeObserver, and Radix's tooltip measures itself with one
// as soon as a focused button opens it. Assigned rather than stubbed, so
// vi.unstubAllGlobals below does not take it away after the first test.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  // jsdom has no matchMedia, and the sidebar asks it whether it is on a
  // phone. Stubbed per test, since the afterEach unstubs globals; a spec can
  // still stub its own answer over this one.
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )

  // The zustand store is a module singleton, so state survives between tests
  // and whichever ran first would silently decide the result of the next.
  // Replaced with the store's own initial state, actions included, so a new
  // key never has to be listed here too.
  useChatStore.setState(useChatStore.getInitialState(), true)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
