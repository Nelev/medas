import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { AppSidebar } from "@/components/app-sidebar"
import { SidebarProvider } from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import type { ConversationSummary } from "@/model/Conversation"
import { conversationList } from "@/test/fixtures"

// AppSidebar is an async Server Component: awaited here as a function, then
// rendered inside the providers the root layout and the page give it.
const renderSidebar = async (conversations: ConversationSummary[]) =>
  render(
    <TooltipProvider>
      <SidebarProvider>
        {await AppSidebar({ conversations: Promise.resolve(conversations) })}
      </SidebarProvider>
    </TooltipProvider>,
  )

describe("AppSidebar", () => {
  it("lists each past conversation by its title", async () => {
    await renderSidebar(conversationList)

    for (const c of conversationList) {
      expect(screen.getByText(c.title)).toBeInTheDocument()
    }
  })

  it("collapses to an icon rail, keeping its toggle on screen", async () => {
    const { container } = await renderSidebar(conversationList)
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

  it("says so when there are none yet", async () => {
    await renderSidebar([])

    expect(screen.getByText("No conversations yet")).toBeInTheDocument()
  })
})
