'use client';

import { ChatList } from '@/components/chat/chat-list';
import { ChatWindow } from '@/components/chat/chat-window';
import { ContextPanel } from '@/components/chat/context-panel';
import { InboxPanelsProvider, useInboxPanels } from '@/contexts/InboxPanelsContext';
import { PanelLeftOpen, Menu, Plus, Search } from 'lucide-react';

function AdminInboxContent() {
  const { chatListCollapsed, contextCollapsed, setChatListCollapsed, setContextCollapsed } = useInboxPanels();

  return (
    <div className="flex h-full">
      {chatListCollapsed ? (
        <div className="hidden md:flex w-14 shrink-0 flex-col items-center gap-1 border-r border-border bg-panel py-4">
          <button
            type="button"
            onClick={() => setChatListCollapsed(false)}
            className="rounded p-2.5 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="Expand conversations"
          >
            <Menu className="h-5 w-5" />
          </button>
          <button
            type="button"
            className="rounded p-2.5 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="New chat"
          >
            <Plus className="h-5 w-5" />
          </button>
          <button
            type="button"
            className="rounded p-2.5 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="Search"
          >
            <Search className="h-5 w-5" />
          </button>
        </div>
      ) : (
        <div className="hidden md:block w-chatlist-tablet lg:w-chatlist-laptop xl:w-chatlist-desktop 2xl:w-chatlist-ultrawide border-r border-border bg-panel shrink-0">
          <ChatList />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <ChatWindow />
      </div>

      {contextCollapsed ? (
        <div className="hidden lg:flex w-12 shrink-0 flex-col items-center border-l border-border bg-panel pt-4">
          <button
            type="button"
            onClick={() => setContextCollapsed(false)}
            className="rounded p-2 text-text-secondary hover:bg-white hover:text-primary transition-colors"
            title="Expand context"
          >
            <PanelLeftOpen className="h-5 w-5" />
          </button>
        </div>
      ) : (
        <div className="hidden lg:block w-context-laptop xl:w-context-desktop 2xl:w-context-ultrawide border-l border-border bg-panel shrink-0">
          <ContextPanel />
        </div>
      )}
    </div>
  );
}

export default function AdminInbox() {
  return (
    <InboxPanelsProvider>
      <AdminInboxContent />
    </InboxPanelsProvider>
  );
}
