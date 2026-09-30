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

// One spec per component the prompt offers, minimal: props a model might
// leave out are left out here too.
const single = (type: string, props: object) => ({
  root: "e",
  elements: { e: { type, props, children: [] } },
})

describe("ReplyUI component set", () => {
  it.each([
    ["Heading", { text: "Section" }, "Section"],
    ["Text", { text: "Next visit" }, "Next visit"],
    ["Badge", { text: "Severe" }, "Severe"],
    [
      "Alert",
      { title: "Seek care sooner", type: "warning" },
      "Seek care sooner",
    ],
    ["Progress", { value: 40, max: 100, label: "Result" }, "Result"],
    ["Accordion", { items: [{ title: "Notes", content: "Detail" }] }, "Notes"],
    ["Collapsible", { title: "More" }, "More"],
  ])("draws %s", (type, props, text) => {
    render(<ReplyUI spec={single(type, props)} />)

    expect(screen.getByText(text)).toBeInTheDocument()
  })

  it("lays out a warning above a card holding a table", () => {
    render(
      <ReplyUI
        spec={{
          root: "s",
          elements: {
            s: { type: "Stack", props: {}, children: ["a", "g", "sep"] },
            a: {
              type: "Alert",
              props: { title: "On your allergy list", type: "warning" },
              children: [],
            },
            g: { type: "Grid", props: { columns: 2 }, children: ["c"] },
            c: { type: "Card", props: { title: "Record" }, children: ["t"] },
            t: {
              type: "Table",
              props: { columns: ["Substance"], rows: [["Ibuprofen"]] },
              children: [],
            },
            sep: { type: "Separator", props: {}, children: [] },
          },
        }}
      />,
    )

    expect(screen.getByText("On your allergy list")).toBeInTheDocument()
    expect(screen.getByRole("table")).toHaveTextContent("Ibuprofen")
  })

  it.each(["Image", "Avatar", "Link", "Button", "Tabs", "Input", "Carousel"])(
    "drops %s, which the catalog leaves out",
    (type) => {
      const { container } = render(
        <ReplyUI
          spec={single(type, { text: "x", src: "https://x.test/a.png" })}
        />,
      )

      expect(container).toBeEmptyDOMElement()
    },
  )
})
