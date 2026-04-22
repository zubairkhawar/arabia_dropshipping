'use client';

import { useState, useMemo, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { useInboxPanels } from '@/contexts/InboxPanelsContext';
import { useInboxConversations } from '@/contexts/InboxConversationsContext';
import { ChevronDown } from 'lucide-react';
import { useAgentSearch } from '@/contexts/AgentSearchContext';
import { useTenantTimezone } from '@/contexts/TenantTimezoneContext';
import {
  formatConversationListTime,
  normalizePhoneDedupeKey,
  parseBackendUtcDate,
} from '@/lib/tenant-time';
import { readAuthAgentId } from '@/lib/agent-session-storage';

type ConversationStatus = 'active' | 'resolved' | 'pending';

interface Conversation {
  id: number;
  customerName: string;
  customerPhone?: string;
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
  /** True when last message is from customer and agent has not replied yet. Only live conversations. */
  isNewLead?: boolean;
  lastActivityIso?: string | null;
}

const defaultConversations: Conversation[] = [
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
    isNewLead: true,
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
    isNewLead: true,
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
];

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const TENANT_ID = 1;

type InboxSearchResult = {
  id: number;
  customer_name: string;
  customer_phone?: string | null;
  last_activity_at?: string | null;
  match_snippet?: string | null;
  unread_count: number;
};

type DedupeRow = {
  id: number;
  customerPhone?: string;
  customerId: string;
  status: ConversationStatus;
  lastActivityIso?: string | null;
};

function activityTimeMs(row: DedupeRow): number {
  return parseBackendUtcDate(row.lastActivityIso ?? undefined)?.getTime() ?? 0;
}

/**
 * Legacy data can have two rows per WhatsApp number (old closed + new active).
 * Admin UI must show one thread per customer at a time.
 */
function dedupeAdminInboxByCustomerPhone<T extends DedupeRow>(rows: T[]): T[] {
  const byKey = new Map<string, T[]>();
  for (const c of rows) {
    const key = normalizePhoneDedupeKey(c.customerPhone) ?? `cid:${c.customerId}`;
    const arr = byKey.get(key) ?? [];
    arr.push(c);
    byKey.set(key, arr);
  }
  const out: T[] = [];
  for (const [, group] of byKey) {
    if (group.length === 1) {
      out.push(group[0]);
      continue;
    }
    const actives = group.filter((c) => c.status === 'active');
    if (actives.length > 0) {
      actives.sort((a, b) => activityTimeMs(b) - activityTimeMs(a) || b.id - a.id);
      out.push(actives[0]);
      continue;
    }
    const resolved = group.filter((c) => c.status === 'resolved');
    if (resolved.length > 0) {
      resolved.sort((a, b) => activityTimeMs(b) - activityTimeMs(a) || b.id - a.id);
      out.push(resolved[0]);
      continue;
    }
    const rest = [...group].sort((a, b) => activityTimeMs(b) - activityTimeMs(a) || b.id - a.id);
    out.push(rest[0]);
  }
  return out;
}

export function ChatList() {
  const { timeZone } = useTenantTimezone();

  const formatSearchTime = (iso?: string | null): string => {
    if (!iso) return '—';
    const d = parseBackendUtcDate(iso) ?? new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    const diff = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    return formatConversationListTime(iso, timeZone);
  };
  const inboxPanels = useInboxPanels();
  const pathname = usePathname();
  const inboxConv = useInboxConversations();
  const [localSelectedId, setLocalSelectedId] = useState<number | null>(1);
  const [localConversations] = useState<Conversation[]>(defaultConversations);
  const [liveOpen, setLiveOpen] = useState(true);
  const [closedOpen, setClosedOpen] = useState(true);
  const { inboxQuery } = useAgentSearch();
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<InboxSearchResult[]>([]);

  const isAgentInbox = pathname?.startsWith('/agent/inbox');
  const conversations = inboxConv ? inboxConv.conversations : localConversations;
  const selectedId = inboxConv ? inboxConv.selectedId : localSelectedId;
  const setSelectedId = inboxConv ? inboxConv.setSelectedId : setLocalSelectedId;

  const view: 'live' | 'closed' = useMemo(() => {
    if (pathname?.startsWith('/admin/inbox/closed')) return 'closed';
    return 'live';
  }, [pathname]);
  const isAdminInbox = pathname?.startsWith('/admin/inbox');
  const isAdminLivePage = pathname?.startsWith('/admin/inbox/live');
  const isAdminClosedPage = pathname?.startsWith('/admin/inbox/closed');

  const sourceConversations = useMemo(() => {
    if (isAgentInbox) return conversations;
    if (isAdminInbox) return dedupeAdminInboxByCustomerPhone(conversations);
    return conversations;
  }, [conversations, isAgentInbox, isAdminInbox]);

  const filteredConversations = useMemo(() => {
    let list = sourceConversations;

    // Admin: one bucket per route (DB-backed). Live = active + assigned agent. Closed = resolved/closed.
    // sourceConversations is deduped by phone so legacy duplicate rows do not appear in two buckets.
    if (!isAgentInbox) {
      if (view === 'live') {
        list = list.filter((c) => c.handlerType === 'agent' && c.status === 'active');
      } else {
        list = list.filter((c) => c.status === 'resolved');
      }
    }

    return [...list].sort((a, b) => b.id - a.id);
  }, [sourceConversations, view, isAgentInbox]);

  // Clear selection when the selected conversation is not in the current view.
  // For agents: the conversation may no longer be assigned (e.g. after customer "reset").
  // For admin: the conversation may not match the active filter (bot/live/closed).
  useEffect(() => {
    if (selectedId == null) return;
    if (isAgentInbox) {
      // Skip while the initial conversation list is still loading.
      if (inboxConv?.isLoading) return;
      const inList = conversations.some((c) => c.id === selectedId);
      if (!inList) {
        setSelectedId(conversations[0]?.id ?? null);
      }
    } else if (isAdminInbox) {
      const inView = filteredConversations.some((c) => c.id === selectedId);
      if (!inView) {
        setSelectedId(filteredConversations[0]?.id ?? null);
      }
    }
  }, [filteredConversations, conversations, selectedId, isAdminInbox, isAgentInbox, setSelectedId, inboxConv?.isLoading]);

  const liveConversations = filteredConversations.filter((c) => c.status === 'active');
  const closedConversations = filteredConversations.filter((c) => c.status === 'resolved');
  const hasAnyInboxConversation =
    liveConversations.length > 0 || closedConversations.length > 0;
  const activeSearch = inboxQuery.trim();
  const localFallbackResults = useMemo(() => {
    const q = activeSearch.toLowerCase();
    if (!q) return [] as InboxSearchResult[];
    return sourceConversations
      .filter((c) => {
        return (
          c.customerName.toLowerCase().includes(q) ||
          c.customerId.toLowerCase().includes(q) ||
          c.lastMessage.toLowerCase().includes(q)
        );
      })
      .slice(0, 50)
      .map((c) => ({
        id: c.id,
        customer_name: c.customerName,
        customer_phone: null,
        last_activity_at: null,
        match_snippet: c.lastMessage || `Conversation ${c.customerId}`,
        unread_count: c.unread,
      }));
  }, [activeSearch, sourceConversations]);
  const displayedSearchResults =
    searchResults.length > 0 ? searchResults : !searchLoading ? localFallbackResults : [];

  useEffect(() => {
    if (!isAgentInbox) return;
    const aid = readAuthAgentId();
    const q = activeSearch;
    if (!q) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }
    if (!aid) {
      setSearchLoading(false);
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    const timer = window.setTimeout(() => {
      const url = new URL(`${API_BASE}/api/messaging/conversations/search`);
      url.searchParams.set('tenant_id', String(TENANT_ID));
      url.searchParams.set('agent_id', String(Number(aid)));
      url.searchParams.set('q', q);
      url.searchParams.set('limit', '50');
      void fetch(url.toString())
        .then((r) => (r.ok ? r.json() : Promise.resolve([])))
        .then((rows: InboxSearchResult[]) => setSearchResults(Array.isArray(rows) ? rows : []))
        .catch(() => setSearchResults([]))
        .finally(() => setSearchLoading(false));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [activeSearch, isAgentInbox]);

  const renderHighlighted = (text: string, query: string) => {
    if (!query) return text;
    const i = text.toLowerCase().indexOf(query.toLowerCase());
    if (i < 0) return text;
    return (
      <>
        {text.slice(0, i)}
        <span className="rounded-sm bg-yellow-200 px-0.5 font-semibold text-text-primary">
          {text.slice(i, i + query.length)}
        </span>
        {text.slice(i + query.length)}
      </>
    );
  };

  return (
    <div className="flex flex-col h-full">
      <div
        className={`flex-1 overflow-y-auto${isAdminInbox ? ' admin-no-scrollbar' : ''}`}
      >
          <div className="p-2 space-y-3">
            {activeSearch && (
              <div className="space-y-2">
                <p className="px-1 text-[11px] font-semibold text-text-muted uppercase tracking-wide">
                  Search results for "{activeSearch}"
                  {searchLoading ? '...' : ` (${displayedSearchResults.length})`}
                </p>
                {searchLoading ? (
                  <p className="px-2 py-2 text-xs text-text-muted">Searching…</p>
                ) : displayedSearchResults.length === 0 ? (
                  <div className="px-2 py-3 rounded-lg border border-border bg-white">
                    <p className="text-sm text-text-primary">No results found for "{activeSearch}"</p>
                    <p className="text-xs text-text-muted mt-1">Try different words or check spelling.</p>
                  </div>
                ) : (
                  <ul className="space-y-1">
                    {displayedSearchResults.map((r) => {
                      const isSelected = selectedId === r.id;
                      const snippet = (r.match_snippet || '').trim() || 'Open conversation';
                      return (
                        <li key={`search-${r.id}`}>
                          <button
                            type="button"
                            onClick={() => setSelectedId(r.id)}
                            className={`w-full text-left p-3 rounded-lg border transition-colors ${
                              isSelected
                                ? 'bg-primary text-white border-primary'
                                : 'bg-white hover:bg-panel border-border'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <span className="text-sm font-medium truncate">{r.customer_name}</span>
                              <span className={`text-xs ${isSelected ? 'text-white/80' : 'text-text-muted'}`}>
                                {formatSearchTime(r.last_activity_at)}
                              </span>
                            </div>
                            {r.customer_phone && (
                              <p className={`text-[11px] mb-0.5 ${isSelected ? 'text-white/80' : 'text-text-muted'}`}>
                                {renderHighlighted(r.customer_phone, activeSearch)}
                              </p>
                            )}
                            <p className={`text-xs truncate ${isSelected ? 'text-white/90' : 'text-text-secondary'}`}>
                              {renderHighlighted(snippet, activeSearch)}
                            </p>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            )}
            {!activeSearch && (
              <>
            {isAgentInbox && inboxConv?.isLoading ? (
              <div className="space-y-2 px-1">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <div
                    key={i}
                    className="h-[76px] rounded-lg bg-border/60 animate-pulse"
                    style={{ animationDelay: `${i * 60}ms` }}
                  />
                ))}
              </div>
            ) : null}

            {/* ── Agent Inbox: Live Conversations ── */}
            {isAgentInbox && !(inboxConv?.isLoading) && (
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
                        <div className="flex items-start justify-between gap-2 mb-1">
                          <span
                            className={`text-sm font-medium truncate flex-1 min-w-0 flex items-center gap-1.5 ${
                              isSelected ? 'text-white' : 'text-text-primary'
                            }`}
                          >
                            {conv.customerName}
                            {conv.unread > 0 && (
                              <span
                                className={`shrink-0 min-w-[1.25rem] h-5 px-1.5 rounded-full flex items-center justify-center text-[10px] font-semibold ${
                                  isSelected
                                    ? 'bg-white/25 text-white'
                                    : 'bg-primary text-white'
                                }`}
                              >
                                {conv.unread}
                              </span>
                            )}
                          </span>
                          <span
                            className={`text-xs flex-shrink-0 ${
                              isSelected ? 'text-white/80' : 'text-text-muted'
                            }`}
                          >
                            {conv.lastActivityAt}
                          </span>
                        </div>
                        {conv.customerPhone && (
                          <p
                            className={`text-[11px] truncate mb-0.5 ${
                              isSelected ? 'text-white/85' : 'text-text-muted'
                            }`}
                          >
                            {conv.customerPhone}
                          </p>
                        )}
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

            {/* ── Agent Inbox: Closed Conversations ── */}
            {isAgentInbox && !(inboxConv?.isLoading) && (
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
                        <div className="flex items-start justify-between gap-2 mb-1">
                          <span
                            className={`text-sm font-medium truncate flex-1 min-w-0 flex items-center gap-1.5 ${
                              isSelected ? 'text-white' : 'text-text-primary'
                            }`}
                          >
                            {conv.customerName}
                            {conv.unread > 0 && (
                              <span
                                className={`shrink-0 min-w-[1.25rem] h-5 px-1.5 rounded-full flex items-center justify-center text-[10px] font-semibold ${
                                  isSelected ? 'bg-white/25 text-white' : 'bg-primary text-white'
                                }`}
                              >
                                {conv.unread}
                              </span>
                            )}
                          </span>
                          <span
                            className={`text-xs flex-shrink-0 ${
                              isSelected ? 'text-white/80' : 'text-text-muted'
                            }`}
                          >
                            {conv.closedAt ?? conv.lastActivityAt}
                          </span>
                        </div>
                        {conv.customerPhone && (
                          <p
                            className={`text-[11px] truncate mb-0.5 ${
                              isSelected ? 'text-white/85' : 'text-text-muted'
                            }`}
                          >
                            {conv.customerPhone}
                          </p>
                        )}
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

            {/* ── Admin: Live Now (agent-handled active conversations) ── */}
            {!isAgentInbox && isAdminLivePage && (
              <div className="space-y-1">
                <p className="px-1 py-1 text-[11px] font-semibold text-text-muted uppercase tracking-wide">
                  Live Agent Conversations — {filteredConversations.length} active
                </p>
                {filteredConversations.map((conv) => {
                  const isSelected = selectedId === conv.id;
                  return (
                    <button
                      key={conv.id}
                      type="button"
                      onClick={() => setSelectedId(conv.id)}
                      className={`w-full text-left p-3 rounded-lg cursor-pointer transition-colors ${
                        isSelected ? 'bg-primary text-white' : 'bg-white hover:bg-panel border border-border'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <span className={`text-sm font-medium truncate flex-1 min-w-0 ${isSelected ? 'text-white' : 'text-text-primary'}`}>
                          {conv.customerName}
                        </span>
                        <span className={`text-xs flex-shrink-0 ${isSelected ? 'text-white/80' : 'text-text-muted'}`}>
                          {conv.lastActivityAt}
                        </span>
                      </div>
                      {conv.customerPhone && (
                        <p className={`text-[11px] truncate mb-0.5 ${isSelected ? 'text-white/85' : 'text-text-muted'}`}>
                          {conv.customerPhone}
                        </p>
                      )}
                      <p className={`text-[11px] truncate mb-0.5 ${isSelected ? 'text-white/80' : 'text-primary'}`}>
                        Agent: {conv.handlerName || 'Assigned'}
                      </p>
                      <p className={`text-xs truncate ${isSelected ? 'text-white/90' : 'text-text-secondary'}`}>
                        {conv.lastMessage}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}

            {/* ── Admin: Closed conversations ── */}
            {!isAgentInbox && isAdminClosedPage && (
              <div className="space-y-1">
                <p className="px-1 py-1 text-[11px] font-semibold text-text-muted uppercase tracking-wide">
                  Closed Conversations — {filteredConversations.length}
                </p>
                {filteredConversations.map((conv) => {
                  const isSelected = selectedId === conv.id;
                  return (
                    <button
                      key={conv.id}
                      type="button"
                      onClick={() => setSelectedId(conv.id)}
                      className={`w-full text-left p-3 rounded-lg cursor-pointer transition-colors ${
                        isSelected ? 'bg-primary text-white' : 'bg-white hover:bg-panel border border-border'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <span className={`text-sm font-medium truncate flex-1 min-w-0 ${isSelected ? 'text-white' : 'text-text-primary'}`}>
                          {conv.customerName}
                        </span>
                        <span className={`text-xs flex-shrink-0 ${isSelected ? 'text-white/80' : 'text-text-muted'}`}>
                          {conv.closedAt ?? conv.lastActivityAt}
                        </span>
                      </div>
                      {conv.customerPhone && (
                        <p className={`text-[11px] truncate mb-0.5 ${isSelected ? 'text-white/85' : 'text-text-muted'}`}>
                          {conv.customerPhone}
                        </p>
                      )}
                      <p className={`text-xs truncate ${isSelected ? 'text-white/90' : 'text-text-secondary'}`}>
                        {conv.lastMessage}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}

            {/* ── Empty state ── */}
            {!(isAgentInbox && inboxConv?.isLoading) && filteredConversations.length === 0 && (
              <div className="px-2 py-4 text-[12px] text-text-muted">
                {isAdminLivePage
                  ? 'No live agent conversations right now.'
                  : isAdminClosedPage
                    ? 'No closed conversations found.'
                    : 'No conversations match this view yet.'}
              </div>
            )}
              </>
            )}
          </div>
      </div>
    </div>
  );
}
