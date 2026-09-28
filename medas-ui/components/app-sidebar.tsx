"use client"

import { ChevronDown, MessagesSquare, SquarePen } from "lucide-react"
import { useEffect, useEffectEvent, useState } from "react"
import { toast } from "sonner"

import { getConversation } from "@/api/chat"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Spinner } from "@/components/ui/spinner"
import { ConversationSummary } from "@/model/Conversation"
import { useChatStore } from "@/store/store"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"

interface AppSidebarProps {
  conversations: ConversationSummary[]
}

const openConversation = async (conversationId: string) => {
  try {
    const { conversationId: id, turns } = await getConversation(conversationId)
    useChatStore.getState().loadConversation(id, turns)
  } catch {
    toast.error("Couldn't open that conversation. Try again.")
  }
}

// The API sends no title yet, so a row is named for the start of its id.
const label = (c: ConversationSummary) =>
  `Conversation ${c.conversationId.slice(0, 8)}`

// The convention chat apps share for a new conversation.
const isNewConversationShortcut = (e: KeyboardEvent) =>
  (e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "o"

// The user's past conversations, newest first; clicking one opens it in the
// chat, which is why this is a client component. Collapses to an icon rail
// rather than off-canvas, so the toggle and the new-conversation action stay
// on screen either way; the list itself leaves the rail, where a column of
// identical icons would say nothing. The conversations group folds too, open
// by default: the label is the trigger, rendered through asChild so it keeps
// the label's look.
export function AppSidebar({ conversations }: AppSidebarProps) {
  const { isMobile, setOpenMobile } = useSidebar()
  const startConversation = useChatStore((s) => s.startConversation)
  // The one the chat is showing: set when a row is opened, or when the first
  // send starts a conversation.
  const openId = useChatStore((s) => s.conversationId)
  // A send in flight would land its reply in whatever the chat shows by
  // then, so switching waits for it.
  const isSending = useChatStore((s) => s.pending !== null)
  // The row being opened, highlighted before its history arrives so the
  // click answers at once. Null once it has.
  const [openingId, setOpeningId] = useState<string | null>(null)
  const activeId = openingId ?? openId
  const isBusy = openingId !== null || isSending

  // On a phone the sidebar is a sheet over the chat; once a choice is made
  // the chat is what the user wants to see.
  const closeSheet = () => {
    if (isMobile) setOpenMobile(false)
  }

  const handleOpen = async (conversationId: string) => {
    if (isBusy) return
    setOpeningId(conversationId)
    await openConversation(conversationId)
    setOpeningId(null)
    closeSheet()
  }

  const handleNew = () => {
    if (isBusy) return
    startConversation()
    closeSheet()
  }

  // The same action from the keyboard. An effect event, so the listener is
  // added once and still sees the current busy state.
  const onShortcut = useEffectEvent(handleNew)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!isNewConversationShortcut(e)) return
      e.preventDefault()
      onShortcut()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  return (
    <Sidebar collapsible="icon">
      {/* No brand here: the chat header beside it already carries it. One
          row, the action and the toggle; in the rail they stack, toggle on
          top. */}
      <SidebarHeader className="flex-row items-center gap-1.5 px-3 pt-3.5 group-data-[collapsible=icon]:flex-col-reverse group-data-[collapsible=icon]:px-2">
        <SidebarMenu className="min-w-0 flex-1">
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip="New conversation"
              aria-keyshortcuts="Control+Shift+O Meta+Shift+O"
              disabled={isBusy}
              className="border-sidebar-border border font-medium group-data-[collapsible=icon]:border-transparent"
              onClick={handleNew}
            >
              <SquarePen aria-hidden />
              <span>New conversation</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <SidebarTrigger />
      </SidebarHeader>

      <SidebarContent className="group-data-[collapsible=icon]:hidden">
        <Collapsible defaultOpen className="group/collapsible">
          <SidebarGroup className="px-3">
            <SidebarGroupLabel
              asChild
              className="text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground px-2.5 transition-colors"
            >
              <CollapsibleTrigger>
                Conversations
                {/* Points right when folded, down when open: the disclosure
                    convention, rather than a flip. */}
                <ChevronDown
                  aria-hidden
                  className="ml-auto -rotate-90 transition-transform group-data-[state=open]/collapsible:rotate-0"
                />
              </CollapsibleTrigger>
            </SidebarGroupLabel>
            <CollapsibleContent>
              <SidebarGroupContent className="pt-1">
                {conversations.length === 0 ? (
                  <div className="flex flex-col items-start gap-1.5 px-2.5 py-6">
                    <MessagesSquare
                      className="text-muted-foreground mb-1 size-5"
                      aria-hidden
                    />
                    <p className="text-sm font-medium">No conversations yet</p>
                    <p className="text-muted-foreground text-xs leading-relaxed">
                      Your chats with Medas will appear here.
                    </p>
                  </div>
                ) : (
                  <SidebarMenu className="gap-0.5">
                    {conversations.map((c) => {
                      const isActive = c.conversationId === activeId
                      const isLoading = c.conversationId === openingId
                      return (
                        <SidebarMenuItem key={c.conversationId}>
                          <SidebarMenuButton
                            isActive={isActive}
                            aria-busy={isLoading || undefined}
                            className="px-2.5"
                            onClick={() => handleOpen(c.conversationId)}
                          >
                            <span className="flex-1 truncate">{label(c)}</span>
                            {isLoading && (
                              <Spinner className="text-muted-foreground size-3.5" />
                            )}
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      )
                    })}
                  </SidebarMenu>
                )}
              </SidebarGroupContent>
            </CollapsibleContent>
          </SidebarGroup>
        </Collapsible>
      </SidebarContent>
    </Sidebar>
  )
}
