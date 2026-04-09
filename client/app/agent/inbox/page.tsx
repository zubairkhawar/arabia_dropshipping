'use client';

import { ChatList } from '@/components/chat/chat-list';
import { ChatWindow } from '@/components/chat/chat-window';
import { ContextPanel } from '@/components/chat/context-panel';
import { InboxAgentPresenceStack } from '@/components/inbox/inbox-agent-presence';
import { InboxPanelsProvider, useInboxPanels } from '@/contexts/InboxPanelsContext';
import { InboxConversationsProvider } from '@/contexts/InboxConversationsContext';
import { useAgents } from '@/contexts/AgentsContext';
import { PanelRightOpen, SquareChevronRight, Search } from 'lucide-react';

function AgentInboxContent() {
  const { chatListCollapsed, contextCollapsed, setChatListCollapsed, setContextCollapsed } = useInboxPanels();
  const { getCurrentAgent, currentAgentId } = useAgents();
  const me = getCurrentAgent();
  const canTransfer =
    Boolean(currentAgentId) && me !== null ? me.canTransferConversations !== false : false;

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      {/* Left: one panel — agent avatars + chat list OR collapsed controls (single border) */}
      {chatListCollapsed ? (
        <div className="relative isolate hidden md:flex w-9 shrink-0 flex-col items-center gap-2 overflow-visible bg-panel px-0.5 py-3 after:pointer-events-none after:absolute after:inset-y-0 after:right-[16px] after:z-20 after:w-px after:bg-border">
          <div className="flex flex-col items-center gap-1.5">
            <InboxAgentPresenceStack />
          </div>
          <div className="h-px w-7 shrink-0 bg-border/60" aria-hidden />
          <button
            type="button"
            onClick={() => setChatListCollapsed(false)}
            className="rounded p-2 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="Expand conversations"
          >
            <SquareChevronRight className="h-5 w-5" />
          </button>
          <button
            type="button"
            className="rounded p-2 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="Search"
          >
            <Search className="h-5 w-5" />
          </button>
        </div>
      ) : (
        <div className="hidden md:flex min-w-0 shrink-0 border-r border-border bg-panel">
          <div className="flex w-14 shrink-0 flex-col items-center gap-1.5 py-3 px-0">
            <InboxAgentPresenceStack />
          </div>
          {/* Explicit divider: avatar rail -> conversations list */}
          <div className="w-px self-stretch bg-border" aria-hidden />
          <div className="min-w-0 w-chatlist-tablet lg:w-chatlist-laptop xl:w-chatlist-desktop 2xl:w-chatlist-ultrawide">
            <ChatList />
          </div>
        </div>
      )}

      {/* Middle panel: chat window (always visible) */}
      <div className="flex min-w-0 flex-1 flex-col min-h-0 overflow-hidden">
        <ChatWindow showTransferControls canTransferConversations={canTransfer} />
      </div>

      {/* Right panel: context or expand strip */}
      {contextCollapsed ? (
        <div className="hidden lg:flex w-12 shrink-0 flex-col items-center border-l border-border bg-panel pt-4">
          <button
            type="button"
            onClick={() => setContextCollapsed(false)}
            className="rounded p-2 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="Expand context"
          >
            <PanelRightOpen className="h-5 w-5" />
          </button>
        </div>
      ) : (
        <div className="hidden lg:block w-context-laptop xl:w-context-desktop 2xl:w-context-ultrawide border-l border-border bg-panel shrink-0 min-h-0 overflow-hidden">
          <ContextPanel />
        </div>
      )}
    </div>
  );
}

export default function AgentInbox() {
  return (
    <InboxPanelsProvider>
      <InboxConversationsProvider>
        <AgentInboxContent />
      </InboxConversationsProvider>
    </InboxPanelsProvider>
  );
}
