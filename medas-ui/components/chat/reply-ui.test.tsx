import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ReplyUI } from "@/components/chat/reply-ui"

const table = (type: string) => ({
  root: "t",
  elements: {
    t: {
      type,
      // No caption: a prop the model leaves out is not an invalid spec.
      props: { columns: ["Drug"], rows: [["Omeprazole"]] },
      children: [],
    },
  },
})

describe("ReplyUI", () => {
  it("draws a spec the catalog accepts", () => {
    render(<ReplyUI spec={table("Table")} fallback="In words" />)

    expect(screen.getByRole("table")).toHaveTextContent("Omeprazole")
    expect(screen.queryByText("In words")).not.toBeInTheDocument()
  })

  it("falls back to the text for a type outside the catalog", () => {
    render(<ReplyUI spec={table("Chart")} fallback="In words" />)

    expect(screen.getByText("In words")).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })
})
