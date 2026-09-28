import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Resolves `@/...` from tsconfig, so the alias is not duplicated here and
    // cannot drift from the one the app builds with.
    tsconfigPaths: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
    // restoreAllMocks only restores spies; this clears every vi.fn's calls
    // between tests, so one test's calls never satisfy the next's assertion.
    clearMocks: true,
    // The app sits beside node_modules and .next; without this Vitest walks
    // into both looking for specs.
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", ".next/**"],
  },
})
