import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { getConversation } from "@/api/chat"

import { AppSidebar } from "@/components/app-sidebar"
import { SidebarProvider } from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import type { ConversationSummary } from "@/model/Conversation"
import { useChatStore } from "@/store/store"
import {
  CONVERSATION_ID,
  conversationList,
  createdConversation,
} from "@/test/fixtures"

vi.mock("@/api/chat", () => ({ getConversation: vi.fn() }))
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }))

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

  it("opens a conversation in the chat when it is clicked", async () => {
    vi.mocked(getConversation).mockResolvedValue({
      conversationId: CONVERSATION_ID,
      turns: createdConversation.messages,
    })
    renderSidebar(conversationList)

    await userEvent.click(
      screen.getByText(`Conversation ${CONVERSATION_ID.slice(0, 8)}`),
    )

    expect(getConversation).toHaveBeenCalledWith(CONVERSATION_ID)
    // Highlighted as the open one; the others are not.
    const [opened, other] = screen.getAllByRole("button", {
      name: /^Conversation /,
    })
    expect(opened).toHaveAttribute("data-active", "true")
    expect(opened).toHaveAttribute("aria-current", "page")
    expect(other).toHaveAttribute("data-active", "false")
    expect(other).not.toHaveAttribute("aria-current")
    expect(useChatStore.getState().conversationId).toBe(CONVERSATION_ID)
    expect(useChatStore.getState().messages).toEqual(
      createdConversation.messages,
    )
  })

  it("keeps the chat as it was, with a toast, when opening fails", async () => {
    vi.mocked(getConversation).mockRejectedValue(new Error("404"))
    renderSidebar(conversationList)

    await userEvent.click(
      screen.getByText(`Conversation ${CONVERSATION_ID.slice(0, 8)}`),
    )

    expect(toast.error).toHaveBeenCalledOnce()
    expect(useChatStore.getState().conversationId).toBe("")
  })

  it("marks the clicked row open while its history loads, once", async () => {
    let resolve!: (value: Awaited<ReturnType<typeof getConversation>>) => void
    vi.mocked(getConversation).mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )
    renderSidebar(conversationList)
    const row = screen.getByRole("button", {
      name: `Conversation ${CONVERSATION_ID.slice(0, 8)}`,
    })

    await userEvent.click(row)
    await userEvent.click(row)

    expect(row).toHaveAttribute("aria-current", "page")
    expect(row).toHaveAttribute("aria-busy", "true")
    expect(getConversation).toHaveBeenCalledOnce()

    resolve({
      conversationId: CONVERSATION_ID,
      turns: createdConversation.messages,
    })

    await waitFor(() => expect(row).not.toHaveAttribute("aria-busy"))
    expect(useChatStore.getState().conversationId).toBe(CONVERSATION_ID)
  })

  it("starts a new conversation, back to the greeting", async () => {
    useChatStore.setState({
      conversationId: CONVERSATION_ID,
      messages: createdConversation.messages,
    })
    renderSidebar(conversationList)

    await userEvent.click(
      screen.getByRole("button", { name: "New conversation" }),
    )

    expect(useChatStore.getState().conversationId).toBe("")
    expect(useChatStore.getState().messages).toEqual([])
  })

  it("starts a new conversation from the keyboard", async () => {
    useChatStore.setState({ conversationId: CONVERSATION_ID })
    renderSidebar(conversationList)

    await userEvent.keyboard("{Control>}{Shift>}o{/Shift}{/Control}")

    expect(useChatStore.getState().conversationId).toBe("")
  })

  it("waits for a send in flight before switching", async () => {
    useChatStore.setState({
      conversationId: CONVERSATION_ID,
      pending: { role: "user", text: "Still on its way" },
    })
    renderSidebar(conversationList)

    expect(
      screen.getByRole("button", { name: "New conversation" }),
    ).toBeDisabled()
    await userEvent.click(
      screen.getAllByRole("button", { name: /^Conversation / })[1],
    )

    expect(getConversation).not.toHaveBeenCalled()
    expect(useChatStore.getState().conversationId).toBe(CONVERSATION_ID)
  })

  it("says so when there are none yet", () => {
    renderSidebar([])

    expect(screen.getByText("No conversations yet")).toBeInTheDocument()
  })
})
