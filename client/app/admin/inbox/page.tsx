'use client';

import { ChatList } from '@/components/chat/chat-list';
import { ChatWindow } from '@/components/chat/chat-window';
import { InboxPanelsProvider, useInboxPanels } from '@/contexts/InboxPanelsContext';
import { PanelRightOpen, SquareChevronRight } from 'lucide-react';

function ContextPanel() {
  return (
    <div className="hidden xl:block w-80 2xl:w-96 shrink-0 border-l border-border bg-panel p-4 transition-all duration-300">
      <h3 className="text-sm font-semibold text-text-primary mb-3">Conversation Context</h3>
      <div className="space-y-3 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Customer</span>
          <span className="font-semibold text-text-primary">Ahmed Ali</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Store</span>
          <span className="font-semibold text-text-primary">My Shopify Store</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Channel</span>
          <span className="font-semibold text-text-primary">WhatsApp</span>
        </div>
      </div>
      <div className="mt-4 border-t border-border pt-4 space-y-3 text-xs">
        <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">
          Assignment
        </p>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Assigned agent</span>
            <span className="font-semibold text-text-primary">Hamza (ID: 1002)</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Status</span>
            <span className="font-semibold text-status-success">Live</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Closed at</span>
            <span className="font-semibold text-text-primary">—</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Resolved by</span>
            <span className="font-semibold text-text-primary">—</span>
          </div>
        </div>
      </div>
      <div className="mt-4 border-t border-border pt-4 space-y-3">
        <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">
          Live Analytics
        </p>
        <div className="space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">AI Resolution Rate</span>
            <span className="font-semibold text-text-primary">87.5%</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Human Agent Load</span>
            <span className="font-semibold text-text-primary">34 active</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Conversations Live</span>
            <span className="font-semibold text-status-info">126</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">At Risk (SLA)</span>
            <span className="font-semibold text-status-error">5</span>
          </div>
        </div>
        <div className="space-y-2 pt-2">
          <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">
            Routing Snapshot
          </p>
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-text-secondary">AI</span>
              <span className="text-text-primary">82%</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/60 overflow-hidden">
              <div className="h-full w-[82%] bg-primary rounded-full" />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-text-secondary">Agents</span>
              <span className="text-text-primary">18%</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/60 overflow-hidden">
              <div className="h-full w-[18%] bg-status-info rounded-full" />
            </div>
          </div>
        </div>
      </div>
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
      <AdminInboxContent />
    </InboxPanelsProvider>
  );
}
