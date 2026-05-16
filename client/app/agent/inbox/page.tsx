'use client';

import { useEffect, useState } from 'react';
import { ChatList } from '@/components/chat/chat-list';
import { ChatWindow } from '@/components/chat/chat-window';
import { ContextPanel } from '@/components/chat/context-panel';
import { InboxAgentPresenceStack } from '@/components/inbox/inbox-agent-presence';
import { InboxPanelsProvider, useInboxPanels } from '@/contexts/InboxPanelsContext';
import { InboxConversationsProvider, useInboxConversations } from '@/contexts/InboxConversationsContext';
import { PanelRightOpen, SquareChevronRight, Search } from 'lucide-react';

function AgentInboxContent() {
  const { chatListCollapsed, contextCollapsed, setChatListCollapsed, setContextCollapsed } = useInboxPanels();
  const inboxConv = useInboxConversations();
  const selectedId = inboxConv?.selectedId ?? null;
  const setSelectedId = inboxConv?.setSelectedId ?? (() => {});

  // Mobile (<426px) push/pop state
  const [isMobile, setIsMobile] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(max-width: 767px)');
    const update = () => setIsMobile(mql.matches);
    update();
    mql.addEventListener('change', update);
    return () => mql.removeEventListener('change', update);
  }, []);

  // ESC closes the mobile drawer.
  useEffect(() => {
    if (!mobileDrawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMobileDrawerOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileDrawerOpen]);

  // Close drawer if user leaves thread view on mobile.
  useEffect(() => {
    if (isMobile && selectedId == null && mobileDrawerOpen) {
      setMobileDrawerOpen(false);
    }
  }, [isMobile, selectedId, mobileDrawerOpen]);

  const mobileShowList = isMobile && selectedId == null;
  const mobileShowThread = isMobile && selectedId != null;

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      {/* Mobile: full-width list when no conversation selected */}
      {mobileShowList && (
        <div className="flex w-full min-w-0 flex-col bg-panel">
          <ChatList />
        </div>
      )}

      {/* Desktop left: avatar rail + chat list (or collapsed strip) */}
      {!isMobile && (
        chatListCollapsed ? (
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
            <div className="w-px self-stretch bg-border" aria-hidden />
            <div className="min-w-0 w-chatlist-tablet lg:w-chatlist-laptop xl:w-chatlist-desktop 2xl:w-chatlist-ultrawide">
              <ChatList />
            </div>
          </div>
        )
      )}

      {/* Middle: chat window. Mobile shows it only when a conversation is selected. */}
      {(!isMobile || mobileShowThread) && (
        <div className="flex min-w-0 flex-1 flex-col min-h-0 overflow-hidden">
          <ChatWindow
            onMobileBack={isMobile ? () => setSelectedId(null) : undefined}
            onOpenMobileDetails={isMobile ? () => setMobileDrawerOpen(true) : undefined}
          />
        </div>
      )}

      {/* Desktop right context panel (visible at xl+) */}
      {!isMobile && (
        contextCollapsed ? (
          <div className="hidden xl:flex w-12 shrink-0 flex-col items-center border-l border-border bg-panel pt-4">
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
          <div className="hidden xl:block xl:w-context-desktop 2xl:w-context-ultrawide border-l border-border bg-panel shrink-0 min-h-0 overflow-hidden">
            <ContextPanel />
          </div>
        )
      )}

      {/* Mobile drawer: right-aligned overlay covering 85% of viewport */}
      {isMobile && (
        <>
          <div
            className={`fixed inset-0 z-40 bg-black/40 transition-opacity duration-200 ${
              mobileDrawerOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
            }`}
            onClick={() => setMobileDrawerOpen(false)}
            aria-hidden
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Conversation details"
            className={`fixed inset-y-0 right-0 z-50 w-[85vw] max-w-sm bg-panel shadow-xl transition-transform duration-200 ${
              mobileDrawerOpen ? 'translate-x-0' : 'translate-x-full'
            }`}
          >
            <ContextPanel onClose={() => setMobileDrawerOpen(false)} />
          </aside>
        </>
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
