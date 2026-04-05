'use client';

import React, { createContext, useContext, useState, useCallback, ReactNode, useEffect, useRef } from 'react';
import { useAgents } from '@/contexts/AgentsContext';
import { usePathname } from 'next/navigation';
import { useAgentPortalRealtime } from '@/contexts/AgentPortalRealtimeContext';
import {
  readAuthAgentId,
  readLastInboxConversationId,
  writeLastInboxConversationId,
  writeInboxLastReadEntry,
} from '@/lib/agent-session-storage';

export type ConversationStatus = 'active' | 'resolved' | 'pending';

export interface InboxConversation {
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
  handlerAgentId?: string;
  closedAt?: string;
  isNewLead?: boolean;
  reopenedAt?: string;
}

export interface InboxMessage {
  id: number;
  content: string;
  sender: 'customer' | 'agent' | 'ai';
  senderName: string;
  timestamp: string;
  sentAt?: string;
  [key: string]: unknown;
}

interface InboxConversationsContextType {
  conversations: InboxConversation[];
  setConversations: React.Dispatch<React.SetStateAction<InboxConversation[]>>;
  selectedId: number | null;
  setSelectedId: (id: number | null) => void;
  isLoading: boolean;
  markAgentReplied: (convId: number) => void;
  closeConversation: (convId: number) => void;
  reopenConversation: (convId: number) => void;
  transferConversation: (
    convId: number,
    toAgentId: string,
    toAgentName: string,
    description?: string,
  ) => void;
  sendConversationToAI: (convId: number) => void;
  getMessages: (convId: number) => InboxMessage[];
  setMessages: (convId: number, messages: InboxMessage[]) => void;
  appendMessage: (convId: number, message: InboxMessage) => void;
  refreshConversations: () => Promise<void>;
  /** When set, the UI can show a thread skeleton for that conversation while messages load. */
  loadingConversationId: number | null;
  inboxHasMoreOlder: (convId: number) => boolean;
  loadOlderInboxMessages: (convId: number) => Promise<void>;
  syncInboxReadState: (convId: number, lastReadMessageId: number) => Promise<void>;
}

const InboxConversationsContext = createContext<InboxConversationsContextType | null>(null);

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const TENANT_ID = 1;

function authJsonHeaders(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('auth_token');
    if (token) h.Authorization = `Bearer ${token}`;
  }
  return h;
}

interface ConversationSummaryApi {
  id: number;
  customer_id: number;
  customer_name?: string | null;
  last_message?: string | null;
  last_activity_at?: string | null;
  channel: 'whatsapp' | 'web' | 'portal';
  status: string;
  agent_id?: number | null;
  unread_count?: number;
}

interface ConversationDetailsApi {
  conversation: {
    id: number;
    customer_id: number;
    channel: 'whatsapp' | 'web' | 'portal';
    status: string;
    agent_id?: number | null;
  };
  messages: Array<{
    id: number;
    content: string;
    sender_type: 'customer' | 'agent' | 'ai';
    created_at: string;
  }>;
  has_more_older?: boolean;
}

function toRelativeTime(iso?: string | null): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '—';
  const diff = Math.max(0, Date.now() - t);
  const min = Math.floor(diff / 60000);
  if (min < 1) return 'Just now';
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

function toConversationStatus(status: string): ConversationStatus {
  if (status === 'closed' || status === 'resolved') return 'resolved';
  if (status === 'pending') return 'pending';
  return 'active';
}

function pickInboxSelection(
  mapped: InboxConversation[],
  lastId: number | null,
  prev: number | null,
): number | null {
  const ids = new Set(mapped.map((c) => c.id));
  if (lastId != null && ids.has(lastId)) return lastId;
  if (prev != null && ids.has(prev)) return prev;
  const sorted = [...mapped].sort((a, b) => b.unread - a.unread);
  if (sorted[0] && sorted[0].unread > 0) return sorted[0].id;
  return mapped[0]?.id ?? null;
}

export function InboxConversationsProvider({ children }: { children: ReactNode }) {
  const { agents, currentAgentId } = useAgents();
  const { subscribe } = useAgentPortalRealtime();
  const pathname = usePathname();
  const isAgentPortal = pathname?.startsWith('/agent/');
  const [conversations, setConversations] = useState<InboxConversation[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selectedIdRef = useRef<number | null>(null);
  const [messagesByConvId, setMessagesByConvId] = useState<Record<number, InboxMessage[]>>({});
  const [inboxMetaByConvId, setInboxMetaByConvId] = useState<Record<number, { hasMoreOlder: boolean }>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [loadingConversationId, setLoadingConversationId] = useState<number | null>(null);

  const mapConversation = useCallback(
    (c: ConversationSummaryApi): InboxConversation => {
      const handlerAgentId = c.agent_id != null ? String(c.agent_id) : undefined;
      const handlerName =
        handlerAgentId != null ? agents.find((a) => a.id === handlerAgentId)?.name : undefined;
      return {
        id: c.id,
        customerName: c.customer_name || `Customer #${c.customer_id}`,
        customerId: `#${c.customer_id}`,
        lastMessage: c.last_message || '',
        lastActivityAt: toRelativeTime(c.last_activity_at),
        unread: typeof c.unread_count === 'number' ? c.unread_count : 0,
        channel: c.channel,
        status: toConversationStatus(c.status),
        handlerType: handlerAgentId ? 'agent' : 'ai',
        handlerName,
        handlerAgentId,
        isNewLead: !handlerAgentId,
      };
    },
    [agents],
  );

  const fetchConversationRowsFromApi = useCallback(async (): Promise<ConversationSummaryApi[]> => {
    const aid = isAgentPortal ? (currentAgentId ?? readAuthAgentId()) : null;
    if (isAgentPortal && !aid) return [];
    const url = new URL(`${API_BASE}/api/messaging/conversations`);
    url.searchParams.set('tenant_id', String(TENANT_ID));
    if (isAgentPortal && aid) {
      url.searchParams.set('agent_id', String(Number(aid)));
    }
    const res = await fetch(url.toString());
    if (!res.ok) return [];
    const rows = (await res.json()) as ConversationSummaryApi[];
    return isAgentPortal ? rows : rows.filter((c) => c.agent_id != null);
  }, [currentAgentId, isAgentPortal]);

  const mapDetailToMessages = useCallback((data: ConversationDetailsApi): InboxMessage[] => {
    return data.messages.map((m) => ({
      id: m.id,
      content: m.content,
      sender: m.sender_type,
      senderName: m.sender_type === 'agent' ? 'You' : m.sender_type === 'customer' ? 'Customer' : 'AI',
      timestamp: new Date(m.created_at).toLocaleTimeString([], {
        hour: 'numeric',
        minute: '2-digit',
      }),
      sentAt: m.created_at,
    }));
  }, []);

  const refreshConversations = useCallback(async () => {
    setIsLoading(true);
    try {
      const rows = await fetchConversationRowsFromApi();
      const mapped = rows.map(mapConversation);
      setConversations(mapped);
      setSelectedId((prev) => pickInboxSelection(mapped, readLastInboxConversationId(), prev));
    } finally {
      setIsLoading(false);
    }
  }, [fetchConversationRowsFromApi, mapConversation]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const loadMessagesForConversation = useCallback(
    async (convId: number) => {
      setLoadingConversationId(convId);
      try {
        const url = new URL(`${API_BASE}/api/messaging/conversations/${convId}`);
        url.searchParams.set('limit', '50');
        const res = await fetch(url.toString());
        if (!res.ok) {
          setMessagesByConvId((prev) => ({ ...prev, [convId]: [] }));
          setInboxMetaByConvId((prev) => ({ ...prev, [convId]: { hasMoreOlder: false } }));
          return;
        }
        const data = (await res.json()) as ConversationDetailsApi;
        const mapped = mapDetailToMessages(data);
        setMessagesByConvId((prev) => ({ ...prev, [convId]: mapped }));
        setInboxMetaByConvId((prev) => ({
          ...prev,
          [convId]: { hasMoreOlder: Boolean(data.has_more_older) },
        }));
      } catch {
        setMessagesByConvId((prev) => ({ ...prev, [convId]: [] }));
        setInboxMetaByConvId((prev) => ({ ...prev, [convId]: { hasMoreOlder: false } }));
      } finally {
        setLoadingConversationId((id) => (id === convId ? null : id));
      }
    },
    [mapDetailToMessages],
  );

  const loadOlderInboxMessages = useCallback(
    async (convId: number) => {
      const list = messagesByConvId[convId];
      if (!list?.length) return;
      const meta = inboxMetaByConvId[convId];
      if (meta && !meta.hasMoreOlder) return;
      const oldestId = list[0].id;
      try {
        const url = new URL(`${API_BASE}/api/messaging/conversations/${convId}`);
        url.searchParams.set('limit', '50');
        url.searchParams.set('before_id', String(oldestId));
        const res = await fetch(url.toString());
        if (!res.ok) return;
        const data = (await res.json()) as ConversationDetailsApi;
        const chunk = mapDetailToMessages(data);
        if (chunk.length === 0) {
          setInboxMetaByConvId((prev) => ({ ...prev, [convId]: { hasMoreOlder: false } }));
          return;
        }
        setMessagesByConvId((prev) => {
          const cur = prev[convId] || [];
          const byId = new Map<number, InboxMessage>();
          for (const m of chunk) byId.set(m.id, m);
          for (const m of cur) byId.set(m.id, m);
          const merged = Array.from(byId.values()).sort((a, b) => a.id - b.id);
          return { ...prev, [convId]: merged };
        });
        setInboxMetaByConvId((prev) => ({
          ...prev,
          [convId]: { hasMoreOlder: Boolean(data.has_more_older) },
        }));
      } catch {
        // ignore
      }
    },
    [messagesByConvId, inboxMetaByConvId, mapDetailToMessages],
  );

  const inboxHasMoreOlder = useCallback(
    (convId: number) => inboxMetaByConvId[convId]?.hasMoreOlder ?? false,
    [inboxMetaByConvId],
  );

  const syncInboxReadState = useCallback(async (convId: number, lastReadMessageId: number) => {
    if (!isAgentPortal) return;
    try {
      const res = await fetch(`${API_BASE}/api/agent-portal/inbox/read-state`, {
        method: 'POST',
        headers: authJsonHeaders(),
        body: JSON.stringify({
          tenant_id: TENANT_ID,
          conversation_id: convId,
          last_read_message_id: lastReadMessageId,
        }),
      });
      if (res.ok) {
        writeInboxLastReadEntry(convId, lastReadMessageId);
        setConversations((prev) =>
          prev.map((c) => (c.id === convId ? { ...c, unread: 0 } : c)),
        );
      }
    } catch {
      // ignore
    }
  }, [isAgentPortal]);

  useEffect(() => {
    return subscribe((msg) => {
      if (msg.type !== 'inbox_message') return;
      const convId = msg.conversation_id;
      if (typeof convId !== 'number') return;
      const raw = msg.message;
      if (!raw || typeof raw !== 'object') return;
      const m = raw as Record<string, unknown>;
      const id = Number(m.id);
      if (!Number.isFinite(id)) return;
      const senderType = m.sender_type === 'customer' || m.sender_type === 'agent' || m.sender_type === 'ai' ? m.sender_type : 'customer';
      const created = typeof m.created_at === 'string' ? m.created_at : new Date().toISOString();
      const im: InboxMessage = {
        id,
        content: String(m.content ?? ''),
        sender: senderType,
        senderName: senderType === 'agent' ? 'You' : senderType === 'customer' ? 'Customer' : 'AI',
        timestamp: new Date(created).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
        sentAt: created,
      };
      const viewing = selectedIdRef.current === convId;
      if (viewing) {
        setMessagesByConvId((prev) => {
          const cur = prev[convId] || [];
          if (cur.some((x) => x.id === im.id)) return prev;
          return { ...prev, [convId]: [...cur, im].sort((a, b) => a.id - b.id) };
        });
        void syncInboxReadState(convId, id);
      } else {
        setConversations((prev) =>
          prev.map((c) =>
            c.id === convId
              ? {
                  ...c,
                  unread: c.unread + 1,
                  lastMessage: im.content,
                  lastActivityAt: 'Just now',
                }
              : c,
          ),
        );
      }
    });
  }, [subscribe, syncInboxReadState]);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      if (!isAgentPortal) {
        setIsLoading(true);
        try {
          const rows = await fetchConversationRowsFromApi();
          if (cancelled) return;
          const mapped = rows.map(mapConversation);
          setConversations(mapped);
          setSelectedId((prev) => pickInboxSelection(mapped, readLastInboxConversationId(), prev));
        } finally {
          if (!cancelled) setIsLoading(false);
        }
        return;
      }

      const aid = currentAgentId ?? readAuthAgentId();
      if (!aid) {
        setConversations([]);
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      const lastId = readLastInboxConversationId();
      const listUrl = new URL(`${API_BASE}/api/messaging/conversations`);
      listUrl.searchParams.set('tenant_id', String(TENANT_ID));
      listUrl.searchParams.set('agent_id', String(Number(aid)));

      try {
        const [rowsRaw, detailData] = await Promise.all([
          fetch(listUrl.toString()).then(async (r) => (r.ok ? r.json() : [])),
          lastId != null
            ? fetch(`${API_BASE}/api/messaging/conversations/${lastId}?limit=50`).then(async (r) =>
                r.ok ? r.json() : null,
              )
            : Promise.resolve(null),
        ]);

        if (cancelled) return;

        const rows = (Array.isArray(rowsRaw) ? rowsRaw : []) as ConversationSummaryApi[];
        const mapped = rows.map(mapConversation);
        setConversations(mapped);

        if (detailData && typeof detailData === 'object' && 'messages' in detailData) {
          const data = detailData as ConversationDetailsApi;
          const convId = data.conversation?.id ?? lastId!;
          const mappedMsgs = mapDetailToMessages(data);
          setMessagesByConvId((prev) => ({ ...prev, [convId]: mappedMsgs }));
          setInboxMetaByConvId((prev) => ({
            ...prev,
            [convId]: { hasMoreOlder: Boolean(data.has_more_older) },
          }));
        }

        setSelectedId((prev) => pickInboxSelection(mapped, lastId, prev));
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [isAgentPortal, currentAgentId, mapConversation, fetchConversationRowsFromApi, mapDetailToMessages]);

  useEffect(() => {
    if (!isAgentPortal || selectedId == null) return;
    writeLastInboxConversationId(selectedId);
  }, [selectedId, isAgentPortal]);

  useEffect(() => {
    if (selectedId == null) return;
    if (messagesByConvId[selectedId] !== undefined) return;
    void loadMessagesForConversation(selectedId);
  }, [selectedId, messagesByConvId, loadMessagesForConversation]);

  const markAgentReplied = useCallback((convId: number) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === convId ? { ...c, isNewLead: false, unread: 0 } : c)),
    );
  }, []);

  const closeConversation = useCallback((convId: number) => {
    const now = new Date();
    const closedAt =
      now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) +
      ', ' +
      now.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    setConversations((prev) =>
      prev.map((c) => (c.id === convId ? { ...c, status: 'resolved', closedAt, unread: 0 } : c)),
    );
    void fetch(`${API_BASE}/api/messaging/conversations/${convId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'closed' }),
    });
  }, []);

  const reopenConversation = useCallback((convId: number) => {
    const now = new Date();
    const reopenedAt = now.toISOString();
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId
          ? {
              ...c,
              status: 'active',
              isNewLead: false,
              unread: 1,
              reopenedAt,
              lastMessage: 'Customer has messaged again.',
              lastActivityAt: 'Just now',
            }
          : c,
      ),
    );
    const systemMsg: InboxMessage = {
      id: Date.now(),
      content: 'Customer messaged again.',
      sender: 'ai',
      senderName: 'System',
      timestamp: now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
      sentAt: now.toISOString(),
    };
    setMessagesByConvId((prev) => ({
      ...prev,
      [convId]: [...(prev[convId] ?? []), systemMsg],
    }));
  }, []);

  const transferConversation = useCallback((convId: number, toAgentId: string, toAgentName: string) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId
          ? {
              ...c,
              handlerType: 'agent',
              handlerAgentId: toAgentId,
              handlerName: toAgentName,
              lastMessage: 'Conversation transferred.',
              lastActivityAt: 'Just now',
            }
          : c,
      ),
    );
    void fetch(`${API_BASE}/api/routing/transfer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: convId,
        target_agent_id: Number(toAgentId),
      }),
    });
  }, []);

  const sendConversationToAI = useCallback((convId: number) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId
          ? { ...c, handlerType: 'ai', handlerName: undefined, handlerAgentId: undefined, lastActivityAt: 'Just now' }
          : c,
      ),
    );
    void fetch(`${API_BASE}/api/messaging/conversations/${convId}/send-to-ai`, {
      method: 'POST',
    });
  }, []);

  const getMessages = useCallback((convId: number) => messagesByConvId[convId] ?? [], [messagesByConvId]);

  const setMessages = useCallback((convId: number, messages: InboxMessage[]) => {
    setMessagesByConvId((prev) => ({ ...prev, [convId]: messages }));
  }, []);

  const appendMessage = useCallback((convId: number, message: InboxMessage) => {
    setMessagesByConvId((prev) => ({
      ...prev,
      [convId]: [...(prev[convId] ?? []), message],
    }));

    if (typeof message.content === 'string' && message.content.trim()) {
      void fetch(`${API_BASE}/api/messaging/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: convId,
          content: message.content,
          sender_type: message.sender,
          channel: 'whatsapp',
        }),
      }).then(() => {
        setConversations((prev) =>
          prev.map((c) =>
            c.id === convId
              ? {
                  ...c,
                  lastMessage: message.content,
                  lastActivityAt: 'Just now',
                  status: c.status === 'resolved' ? 'active' : c.status,
                }
              : c,
          ),
        );
      });
    }
  }, []);

  return (
    <InboxConversationsContext.Provider
      value={{
        conversations,
        setConversations,
        selectedId,
        setSelectedId,
        isLoading,
        markAgentReplied,
        closeConversation,
        reopenConversation,
        transferConversation,
        sendConversationToAI,
        getMessages,
        setMessages,
        appendMessage,
        refreshConversations,
        loadingConversationId,
        inboxHasMoreOlder,
        loadOlderInboxMessages,
        syncInboxReadState,
      }}
    >
      {children}
    </InboxConversationsContext.Provider>
  );
}

export function useInboxConversations() {
  return useContext(InboxConversationsContext);
}
