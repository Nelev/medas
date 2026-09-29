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
    render(<ReplyUI spec={table("Table")} />)

    expect(screen.getByRole("table")).toHaveTextContent("Omeprazole")
  })

  it("draws nothing for a type outside the catalog", () => {
    const { container } = render(<ReplyUI spec={table("Chart")} />)

    expect(container).toBeEmptyDOMElement()
  })
})
