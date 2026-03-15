'use client';

import { useState, useMemo } from 'react';
import { usePathname } from 'next/navigation';
import { useInboxPanels } from '@/contexts/InboxPanelsContext';
import { ChevronDown } from 'lucide-react';

type ConversationStatus = 'active' | 'resolved' | 'pending';

interface Conversation {
  id: number;
  customerName: string;
  customerId: string;
  lastMessage: string;
  lastActivityAt: string;
  unread: number;
  channel: 'whatsapp' | 'web' | 'portal';
  status: ConversationStatus;
  handlerType: 'ai' | 'agent';
  handlerName?: string;
  /** Backend-generated agent ID when handler is an agent. */
  handlerAgentId?: string;
  closedAt?: string;
}

interface AgentAvatar {
  id: string;
  agentId: string;
  name: string;
  initials: string;
  online: boolean;
}

export function ChatList() {
  const inboxPanels = useInboxPanels();
  const pathname = usePathname();
  const [selectedId, setSelectedId] = useState<number | null>(1);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [liveOpen, setLiveOpen] = useState(true);
  const [closedOpen, setClosedOpen] = useState(true);
  const [conversations] = useState<Conversation[]>([
    {
      id: 1,
      customerName: 'Ahmed Ali',
      customerId: '#1234',
      lastMessage: 'Hello, I need help with my order...',
      lastActivityAt: '2m ago',
      unread: 2,
      channel: 'whatsapp',
      status: 'active',
      handlerType: 'ai',
    },
    {
      id: 2,
      customerName: 'Sarah Khan',
      customerId: '#1235',
      lastMessage: 'When will my order be delivered?',
      lastActivityAt: '5m ago',
      unread: 1,
      channel: 'whatsapp',
      status: 'active',
      handlerType: 'agent',
      handlerName: 'Hamza',
      handlerAgentId: '1002',
    },
    {
      id: 3,
      customerName: 'Mohammed Hassan',
      customerId: '#1236',
      lastMessage: 'Thank you for your help!',
      lastActivityAt: '1h ago',
      unread: 0,
      channel: 'whatsapp',
      status: 'resolved',
      handlerType: 'agent',
      handlerName: 'Sarah',
      handlerAgentId: '1003',
      closedAt: '1h ago',
    },
  ]);

  const view: 'all' | 'live' | 'closed' = useMemo(() => {
    if (pathname?.startsWith('/admin/inbox/live')) return 'live';
    if (pathname?.startsWith('/admin/inbox/closed')) return 'closed';
    return 'all';
  }, [pathname]);

  const agents: AgentAvatar[] = useMemo(() => {
    const uniqueAgents = new Map<string, AgentAvatar>();
    conversations.forEach((conv) => {
      if (conv.handlerType === 'agent' && conv.handlerName && conv.handlerAgentId) {
        if (!uniqueAgents.has(conv.handlerAgentId)) {
          uniqueAgents.set(conv.handlerAgentId, {
            id: conv.handlerAgentId,
            agentId: conv.handlerAgentId,
            name: conv.handlerName,
            initials: conv.handlerName
              .split(' ')
              .map((p) => p[0])
              .join('')
              .slice(0, 2)
              .toUpperCase(),
            online: conv.status === 'active',
          });
        }
      }
    });
    return Array.from(uniqueAgents.values());
  }, [conversations]);

  const filteredConversations = useMemo(() => {
    let list = conversations;

    if (view === 'live') {
      list = list.filter((c) => c.status === 'active');
    } else if (view === 'closed') {
      list = list.filter((c) => c.status === 'resolved');
    }

    if (selectedAgentId) {
      list = list.filter(
        (c) => c.handlerType === 'agent' && c.handlerAgentId === selectedAgentId,
      );
    }

    return [...list].sort((a, b) => b.id - a.id);
  }, [conversations, view, selectedAgentId]);

  const liveConversations = filteredConversations.filter((c) => c.status === 'active');
  const closedConversations = filteredConversations.filter((c) => c.status === 'resolved');

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-1 min-h-0">
        {/* Thin vertical agent avatar bar */}
        <div className="w-12 border-r border-border bg-panel flex flex-col items-center pt-4 gap-3">
          {agents.map((agent) => {
            const isActive = agent.id === selectedAgentId;
            return (
              <div key={agent.id} className="relative group">
                <button
                  type="button"
                  onClick={() =>
                    setSelectedAgentId((current) => (current === agent.id ? null : agent.id))
                  }
                  className={`relative w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold transition-colors ${
                    isActive
                      ? 'bg-primary text-white ring-2 ring-white shadow-md'
                      : 'bg-white text-text-primary hover:bg-white/80 border border-border'
                  }`}
                >
                  <span>{agent.initials}</span>
                  <span
                    className={`absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2 border-panel ${
                      agent.online ? 'bg-status-success' : 'bg-text-muted'
                    }`}
                  />
                </button>
                <div className="pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-4 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-150">
                  <div className="rounded-2xl bg-white shadow-xl border border-border px-4 py-3 flex items-center gap-3 min-w-[180px]">
                    <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-sm font-semibold text-primary">
                      {agent.initials}
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-semibold text-text-primary truncate">
                        {agent.name}
                      </span>
                      <span className="text-[10px] font-mono text-text-muted">
                        ID: {agent.agentId}
                      </span>
                      <span className="text-[11px] text-text-muted">
                        {agent.online ? 'Online' : 'Offline'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Conversation list as system activity feed */}
        <div className="flex-1 overflow-y-auto">
          <div className="p-2 space-y-3">
            {liveConversations.length > 0 && (
              <div className="space-y-1">
                <button
                  type="button"
                  className="w-full px-1 py-1 flex items-center justify-between hover:bg-panel rounded"
                  onClick={() => setLiveOpen((open) => !open)}
                >
                  <span className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">
                    Live Conversations
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="text-[11px] text-text-secondary">
                      {liveConversations.length} active
                    </span>
                    <ChevronDown
                      className={`h-3 w-3 text-text-muted transition-transform ${
                        liveOpen ? 'rotate-180' : ''
                      }`}
                    />
                  </span>
                </button>
                {liveOpen &&
                  liveConversations.map((conv) => {
                    const isSelected = selectedId === conv.id;
                    return (
                      <button
                        key={conv.id}
                        type="button"
                        onClick={() => setSelectedId(conv.id)}
                        className={`w-full text-left p-3 rounded-lg cursor-pointer transition-colors ${
                          isSelected
                            ? 'bg-primary text-white'
                            : 'bg-white hover:bg-panel border border-border'
                        }`}
                      >
                        <div className="flex items-start justify-between mb-1">
                          <span
                            className={`text-sm font-medium truncate flex-1 min-w-0 ${
                              isSelected ? 'text-white' : 'text-text-primary'
                            }`}
                          >
                            {conv.customerName}
                          </span>
                          <span
                            className={`text-xs flex-shrink-0 ml-2 ${
                              isSelected ? 'text-white/80' : 'text-text-muted'
                            }`}
                          >
                            {conv.lastActivityAt}
                          </span>
                        </div>
                        <p
                          className={`text-xs truncate ${
                            isSelected ? 'text-white/90' : 'text-text-secondary'
                          }`}
                        >
                          {conv.lastMessage}
                        </p>
                      </button>
                    );
                  })}
              </div>
            )}

            {closedConversations.length > 0 && (
              <div className="space-y-1">
                <button
                  type="button"
                  className="w-full px-1 py-1 flex items-center justify-between mt-2 hover:bg-panel rounded"
                  onClick={() => setClosedOpen((open) => !open)}
                >
                  <span className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">
                    Closed Conversations
                  </span>
                  <span className="flex items-center gap-1">
                    <ChevronDown
                      className={`h-3 w-3 text-text-muted transition-transform ${
                        closedOpen ? 'rotate-180' : ''
                      }`}
                    />
                  </span>
                </button>
                {closedOpen &&
                  closedConversations.map((conv) => {
                    const isSelected = selectedId === conv.id;

                    return (
                      <button
                        key={conv.id}
                        type="button"
                        onClick={() => setSelectedId(conv.id)}
                        className={`w-full text-left p-3 rounded-lg cursor-pointer transition-colors ${
                          isSelected
                            ? 'bg-primary text-white'
                            : 'bg-white hover:bg-panel border border-border'
                        }`}
                      >
                        <div className="flex items-start justify-between mb-1">
                          <span
                            className={`text-sm font-medium truncate flex-1 min-w-0 ${
                              isSelected ? 'text-white' : 'text-text-primary'
                            }`}
                          >
                            {conv.customerName}
                          </span>
                          <span
                            className={`text-xs flex-shrink-0 ml-2 ${
                              isSelected ? 'text-white/80' : 'text-text-muted'
                            }`}
                          >
                            {conv.closedAt ?? conv.lastActivityAt}
                          </span>
                        </div>
                        <p
                          className={`text-xs truncate ${
                            isSelected ? 'text-white/90' : 'text-text-secondary'
                          }`}
                        >
                          {conv.lastMessage}
                        </p>
                      </button>
                    );
                  })}
              </div>
            )}

            {liveConversations.length === 0 && closedConversations.length === 0 && (
              <div className="px-2 py-4 text-[12px] text-text-muted">
                No conversations match this view yet. Adjust the agent selection or try a different
                inbox view.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
