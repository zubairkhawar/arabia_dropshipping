'use client';

import { ChatList } from '@/components/chat/chat-list';
import { ChatWindow } from '@/components/chat/chat-window';
import { InboxPanelsProvider, useInboxPanels } from '@/contexts/InboxPanelsContext';
import { InboxConversationsProvider, useInboxConversations } from '@/contexts/InboxConversationsContext';
import { PanelRightOpen, SquareChevronRight } from 'lucide-react';

function ContextPanel() {
  const inboxConv = useInboxConversations();
  const selected =
    inboxConv?.selectedId != null
      ? inboxConv.conversations.find((c) => c.id === inboxConv.selectedId)
      : null;

  return (
    <div className="hidden xl:block w-80 2xl:w-96 shrink-0 border-l border-border bg-panel p-4 transition-all duration-300">
      <h3 className="text-sm font-semibold text-text-primary mb-3">Conversation Context</h3>
      {selected ? (
        <div className="space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Customer</span>
            <span className="font-semibold text-text-primary">{selected.customerName}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Conversation</span>
            <span className="font-semibold text-text-primary">{selected.customerId}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Channel</span>
            <span className="font-semibold text-text-primary">{selected.channel}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Status</span>
            <span className="font-semibold text-text-primary">{selected.status}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Handler</span>
            <span className="font-semibold text-text-primary">
              {selected.handlerType === 'ai' ? 'AI' : selected.handlerName || 'Agent'}
            </span>
          </div>
        </div>
      ) : (
        <p className="text-xs text-text-muted">Select a conversation to view context.</p>
      )}
    </div>
  );
}

function AdminInboxContent() {
  const { contextCollapsed, setContextCollapsed } = useInboxPanels()!;

  return (
    <div className="flex h-full">
      <div className="hidden md:block w-chatlist-tablet lg:w-chatlist-laptop xl:w-chatlist-desktop 2xl:w-chatlist-ultrawide border-r border-border bg-panel shrink-0">
        <ChatList />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-white">
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-text-primary">Monitoring</span>
            <span className="text-[11px] text-text-secondary">
              Read-only view of live and historical conversations.
            </span>
          </div>
        </div>
        <div className="relative flex-1">
          <ChatWindow readOnly />
        </div>
      </div>

      {contextCollapsed ? (
        <div className="hidden lg:flex w-8 shrink-0 flex-col items-center border-l border-border bg-panel pt-4 transition-all duration-300">
          <button
            type="button"
            onClick={() => setContextCollapsed(false)}
            className="rounded p-2 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="Expand analytics"
          >
            <PanelRightOpen className="h-5 w-5" />
          </button>
        </div>
      ) : (
        <ContextPanel />
      )}
    </div>
  );
}

export default function AdminInbox() {
  return (
    <InboxPanelsProvider>
      <InboxConversationsProvider>
        <AdminInboxContent />
      </InboxConversationsProvider>
    </InboxPanelsProvider>
  );
}
