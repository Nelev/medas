import { ChevronDown, MessageSquare } from "lucide-react"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
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

interface AppSidebarProps {
  conversations: ConversationSummary[]
}

// The API sends no title yet, so a row is named for the start of its id, in
// the mono face the interface keeps for ids.
const label = (c: ConversationSummary) =>
  `Conversation ${c.conversationId.slice(0, 8)}`

// The user's past conversations, newest first. Listed only: opening one is
// not wired up yet. Collapses to an icon rail rather than off-canvas, so the
// toggle in its header stays on screen either way. The conversations group
// folds too, open by default: the label is the trigger, rendered through
// asChild so it keeps the label's look.
export function AppSidebar({ conversations }: AppSidebarProps) {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="flex-row items-center justify-end group-data-[collapsible=icon]:justify-center">
        <SidebarTrigger />
      </SidebarHeader>

      <SidebarContent>
        <Collapsible defaultOpen className="group/collapsible">
          <SidebarGroup>
            <SidebarGroupLabel asChild>
              <CollapsibleTrigger>
                Conversations
                <ChevronDown
                  aria-hidden
                  className="ml-auto transition-transform group-data-[state=open]/collapsible:rotate-180"
                />
              </CollapsibleTrigger>
            </SidebarGroupLabel>
            <CollapsibleContent>
              <SidebarGroupContent>
                {conversations.length === 0 ? (
                  <p className="text-muted-foreground px-2 py-1.5 text-xs group-data-[collapsible=icon]:hidden">
                    No conversations yet
                  </p>
                ) : (
                  <SidebarMenu>
                    {conversations.map((c) => (
                      <SidebarMenuItem key={c.conversationId}>
                        <SidebarMenuButton tooltip={label(c)}>
                          <MessageSquare aria-hidden />
                          <span className="font-mono text-xs">{label(c)}</span>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
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
