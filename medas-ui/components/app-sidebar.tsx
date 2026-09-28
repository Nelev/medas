import { MessageSquare } from "lucide-react"

import { ConversationSummary } from "@/model/Conversation"
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
} from "@/components/ui/sidebar"

// The user's past conversations, newest first. Listed only: opening one is
// not wired up yet.
//
// Collapses to an icon rail rather than off-canvas, so the toggle in its
// header stays on screen either way. Collapsed, each row keeps its icon and
// shows the title as a tooltip.
//
// Takes the list as a promise, so the page can start it alongside its own
// fetch rather than after it.
interface AppSidebarProps {
  conversations: Promise<ConversationSummary[]>
}

export async function AppSidebar(props: AppSidebarProps) {
  const conversations = await props.conversations

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="flex-row items-center justify-end group-data-[collapsible=icon]:justify-center">
        <SidebarTrigger />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Conversations</SidebarGroupLabel>
          <SidebarGroupContent>
            {conversations.length === 0 ? (
              <p className="text-muted-foreground px-2 py-1.5 text-xs group-data-[collapsible=icon]:hidden">
                No conversations yet
              </p>
            ) : (
              <SidebarMenu>
                {conversations.map((c) => (
                  <SidebarMenuItem key={c.conversationId}>
                    <SidebarMenuButton tooltip={c.title}>
                      <MessageSquare aria-hidden />
                      <span>{c.title}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            )}
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  )
}
