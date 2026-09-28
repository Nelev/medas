import { render } from "@testing-library/react"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { LoadErrorToast } from "@/components/chat/load-error-toast"

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }))

describe("LoadErrorToast", () => {
  it("raises one error toast when it mounts", () => {
    render(<LoadErrorToast />)

    expect(toast.error).toHaveBeenCalledOnce()
    expect(toast.error).toHaveBeenCalledWith(
      expect.stringContaining("Couldn't load your conversations"),
    )
  })
})
