import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { AppSidebar } from "@/components/app-sidebar"
import { SidebarProvider } from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import type { ConversationSummary } from "@/model/Conversation"
import { conversationList } from "@/test/fixtures"

// Inside the providers the root layout and the page give it.
const renderSidebar = (conversations: ConversationSummary[]) =>
  render(
    <TooltipProvider>
      <SidebarProvider>
        <AppSidebar conversations={conversations} />
      </SidebarProvider>
    </TooltipProvider>,
  )

describe("AppSidebar", () => {
  it("lists each past conversation by the start of its id", () => {
    renderSidebar(conversationList)

    for (const c of conversationList) {
      expect(
        screen.getByText(`Conversation ${c.conversationId.slice(0, 8)}`),
      ).toBeInTheDocument()
    }
  })

  it("collapses to an icon rail, keeping its toggle on screen", async () => {
    const { container } = renderSidebar(conversationList)
    const sidebar = () => container.querySelector('[data-slot="sidebar"]')

    expect(sidebar()).toHaveAttribute("data-state", "expanded")

    await userEvent.click(
      screen.getByRole("button", { name: "Toggle Sidebar" }),
    )

    expect(sidebar()).toHaveAttribute("data-state", "collapsed")
    expect(
      screen.getByRole("button", { name: "Toggle Sidebar" }),
    ).toBeInTheDocument()
  })

  it("folds the conversations group from its label", async () => {
    renderSidebar(conversationList)
    const first = `Conversation ${conversationList[0].conversationId.slice(0, 8)}`
    const trigger = screen.getByRole("button", { name: "Conversations" })

    expect(trigger).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText(first)).toBeInTheDocument()

    await userEvent.click(trigger)

    expect(trigger).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByText(first)).not.toBeInTheDocument()

    await userEvent.click(trigger)

    expect(screen.getByText(first)).toBeInTheDocument()
  })

  it("says so when there are none yet", () => {
    renderSidebar([])

    expect(screen.getByText("No conversations yet")).toBeInTheDocument()
  })
})
