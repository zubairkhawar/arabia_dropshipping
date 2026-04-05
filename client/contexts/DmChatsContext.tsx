'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { useAgents } from '@/contexts/AgentsContext';
import { useNotifications } from '@/contexts/NotificationsContext';
import { readAuthAgentId, readLastDmPrefs, writeLastDmPrefs } from '@/lib/agent-session-storage';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const TENANT_ID = 1;

const DM_UNREAD_STORAGE_KEY = 'dm-unread-by-slug:v1';

function readDmUnreadMap(): Record<string, number> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = sessionStorage.getItem(DM_UNREAD_STORAGE_KEY);
    if (!raw) return {};
    const p = JSON.parse(raw) as Record<string, number>;
    return p && typeof p === 'object' ? p : {};
  } catch {
    return {};
  }
}

function writeDmUnreadMap(m: Record<string, number>) {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(DM_UNREAD_STORAGE_KEY, JSON.stringify(m));
  } catch {
    // ignore
  }
}

function parseDmMessagesPayload(data: unknown): {
  rows: Array<{ id: number; sender_agent_id: number; content: string; created_at: string }>;
  hasMoreOlder: boolean;
} {
  if (Array.isArray(data)) {
    return { rows: data, hasMoreOlder: false };
  }
  if (data && typeof data === 'object' && 'messages' in data) {
    const o = data as { messages: unknown; has_more_older?: boolean };
    const arr = Array.isArray(o.messages) ? o.messages : [];
    return { rows: arr as Array<{ id: number; sender_agent_id: number; content: string; created_at: string }>, hasMoreOlder: Boolean(o.has_more_older) };
  }
  return { rows: [], hasMoreOlder: false };
}

export interface DmConversation {
  id: string;
  peerAgentId: string;
  slug: string;
  name: string;
  lastMessageAt: string;
}

export interface DmMessage {
  id: number;
  content: string;
  senderAgentId: string;
  senderName: string;
  createdAt: string;
}

interface DmChatsContextType {
  conversations: DmConversation[];
  addOrUpdateConversation: (peerAgentId: string, slug: string, name: string) => Promise<void>;
  removeConversation: (slug: string) => void;
  getConversationBySlug: (slug: string) => DmConversation | undefined;
  getMessagesBySlug: (slug: string) => DmMessage[];
  /** First page (latest 50). Replaces thread. */
  loadInitialDmThread: (slug: string) => Promise<void>;
  /** @deprecated use loadInitialDmThread */
  loadMessagesBySlug: (slug: string) => Promise<void>;
  loadOlderDmMessages: (slug: string) => Promise<void>;
  fetchDmMessagesSince: (slug: string, sinceIso: string) => Promise<void>;
  mergeIncomingDmMessage: (slug: string, row: { id: number; sender_agent_id: number; content: string; created_at: string }) => void;
  dmHasMoreOlder: (slug: string) => boolean;
  sendMessageBySlug: (slug: string, content: string) => Promise<void>;
  getConversations: () => DmConversation[];
  refreshConversations: () => Promise<void>;
  isDmListLoading: boolean;
  loadingDmSlug: string | null;
  loadingOlderDmSlug: string | null;
  getDmUnreadCount: (slug: string) => number;
  reportDmUnread: (slug: string) => void;
  clearDmUnread: (slug: string) => void;
}

const DmChatsContext = createContext<DmChatsContextType | undefined>(undefined);

export function DmChatsProvider({ children }: { children: ReactNode }) {
  const { getCurrentAgent } = useAgents();
  const notifications = useNotifications();
  const currentAgentId = getCurrentAgent()?.id ?? readAuthAgentId();
  const [conversations, setConversations] = useState<DmConversation[]>([]);
  const [messagesBySlug, setMessagesBySlug] = useState<Record<string, DmMessage[]>>({});
  const [dmMetaBySlug, setDmMetaBySlug] = useState<Record<string, { hasMoreOlder: boolean }>>({});
  const [dmUnreadBySlug, setDmUnreadBySlug] = useState<Record<string, number>>(() => readDmUnreadMap());
  const [isDmListLoading, setIsDmListLoading] = useState(true);
  const [loadingDmSlug, setLoadingDmSlug] = useState<string | null>(null);
  const [loadingOlderDmSlug, setLoadingOlderDmSlug] = useState<string | null>(null);

  const mapRowsToMessages = useCallback(
    (
      slug: string,
      rows: Array<{ id: number; sender_agent_id: number; content: string; created_at: string }>,
    ): DmMessage[] => {
      const conv = conversations.find((c) => c.slug === slug);
      const peerName = conv?.name || 'Agent';
      return rows.map((row) => ({
        id: row.id,
        senderAgentId: String(row.sender_agent_id),
        senderName: String(row.sender_agent_id) === String(currentAgentId) ? 'You' : peerName,
        content: row.content,
        createdAt: row.created_at,
      }));
    },
    [conversations, currentAgentId],
  );

  const refreshConversations = useCallback(async () => {
    if (!currentAgentId) {
      setConversations([]);
      setMessagesBySlug({});
      setDmMetaBySlug({});
      setIsDmListLoading(false);
      return;
    }
    setIsDmListLoading(true);
    const last = readLastDmPrefs();
    const listUrl = new URL(`${API_BASE}/api/internal-dm/conversations`);
    listUrl.searchParams.set('tenant_id', String(TENANT_ID));
    listUrl.searchParams.set('agent_id', String(Number(currentAgentId)));

    try {
      const [listRes, messagesRes] = await Promise.all([
        fetch(listUrl.toString()),
        last
          ? fetch(
              `${API_BASE}/api/internal-dm/conversations/${last.conversationId}/messages?agent_id=${encodeURIComponent(
                String(Number(currentAgentId)),
              )}&limit=50`,
            )
          : Promise.resolve({ ok: false } as Response),
      ]);

      if (!listRes.ok) return;
      const rows = (await listRes.json()) as Array<{
        id: number;
        peer: { agent_id: number; name: string };
        last_message_at: string | null;
      }>;
      const mapped: DmConversation[] = rows.map((row) => {
        const name = row.peer.name || `Agent ${row.peer.agent_id}`;
        const slug =
          name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '') || String(row.peer.agent_id);
        return {
          id: String(row.id),
          peerAgentId: String(row.peer.agent_id),
          slug,
          name,
          lastMessageAt: row.last_message_at || new Date().toISOString(),
        };
      });
      setConversations(mapped);

      if (messagesRes.ok && last) {
        const slugFromList = mapped.find((c) => c.id === last.conversationId)?.slug ?? last.slug;
        const raw = await messagesRes.json();
        const { rows: msgRows, hasMoreOlder } = parseDmMessagesPayload(raw);
        const conv = mapped.find((c) => c.id === last.conversationId) ?? mapped.find((c) => c.slug === last.slug);
        const peerName = conv?.name || 'Agent';
        const mappedMsgs: DmMessage[] = msgRows.map((row) => ({
          id: row.id,
          senderAgentId: String(row.sender_agent_id),
          senderName:
            String(row.sender_agent_id) === currentAgentId
              ? 'You'
              : peerName,
          content: row.content,
          createdAt: row.created_at,
        }));
        setMessagesBySlug((prev) => ({ ...prev, [slugFromList]: mappedMsgs }));
        setDmMetaBySlug((prev) => ({ ...prev, [slugFromList]: { hasMoreOlder } }));
        writeLastDmPrefs(last.conversationId, slugFromList);
      }
    } catch {
      // ignore network errors
    } finally {
      setIsDmListLoading(false);
    }
  }, [currentAgentId]);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  const addOrUpdateConversation = useCallback(async (peerAgentId: string, slug: string, name: string) => {
    if (!currentAgentId) return;
    try {
      const res = await fetch(`${API_BASE}/api/internal-dm/conversations/find-or-create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: TENANT_ID,
          agent_id: Number(currentAgentId),
          peer_agent_id: Number(peerAgentId),
        }),
      });
      if (!res.ok) return;
      const row = (await res.json()) as {
        id: number;
        peer: { agent_id: number; name: string };
        last_message_at: string | null;
      };
      setConversations((prev) => {
        const rest = prev.filter((c) => c.slug !== slug);
        const updated: DmConversation[] = [
          {
            id: String(row.id),
            peerAgentId: String(row.peer.agent_id),
            slug,
            name: row.peer.name || name,
            lastMessageAt: row.last_message_at || new Date().toISOString(),
          },
          ...rest,
        ].sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime());
        return updated;
      });
    } catch {
      // ignore network errors
    }
  }, [currentAgentId]);

  const removeConversation = useCallback((slug: string) => {
    setConversations((prev) => prev.filter((c) => c.slug !== slug));
    setMessagesBySlug((prev) => {
      const next = { ...prev };
      delete next[slug];
      return next;
    });
    setDmMetaBySlug((prev) => {
      const next = { ...prev };
      delete next[slug];
      return next;
    });
    setDmUnreadBySlug((prev) => {
      const next = { ...prev };
      delete next[slug];
      writeDmUnreadMap(next);
      return next;
    });
  }, []);

  const getConversationBySlug = useCallback(
    (slug: string) => conversations.find((c) => c.slug === slug),
    [conversations],
  );

  const loadInitialDmThread = useCallback(
    async (slug: string) => {
      if (!currentAgentId) return;
      const conversation = conversations.find((c) => c.slug === slug);
      if (!conversation) return;
      setLoadingDmSlug(slug);
      try {
        const url = new URL(`${API_BASE}/api/internal-dm/conversations/${conversation.id}/messages`);
        url.searchParams.set('agent_id', String(Number(currentAgentId)));
        url.searchParams.set('limit', '50');
        const res = await fetch(url.toString());
        if (!res.ok) return;
        const raw = await res.json();
        const { rows, hasMoreOlder } = parseDmMessagesPayload(raw);
        const mapped = mapRowsToMessages(slug, rows);
        setMessagesBySlug((prev) => ({ ...prev, [slug]: mapped }));
        setDmMetaBySlug((prev) => ({ ...prev, [slug]: { hasMoreOlder } }));
        writeLastDmPrefs(conversation.id, slug);
      } catch {
        // ignore
      } finally {
        setLoadingDmSlug((s) => (s === slug ? null : s));
      }
    },
    [conversations, currentAgentId, mapRowsToMessages],
  );

  const loadOlderDmMessages = useCallback(
    async (slug: string) => {
      if (!currentAgentId) return;
      const conversation = conversations.find((c) => c.slug === slug);
      const list = messagesBySlug[slug];
      if (!conversation || !list?.length) return;
      const meta = dmMetaBySlug[slug];
      if (meta && !meta.hasMoreOlder) return;
      const oldestId = list[0].id;
      setLoadingOlderDmSlug(slug);
      try {
        const url = new URL(`${API_BASE}/api/internal-dm/conversations/${conversation.id}/messages`);
        url.searchParams.set('agent_id', String(Number(currentAgentId)));
        url.searchParams.set('limit', '50');
        url.searchParams.set('before_id', String(oldestId));
        const res = await fetch(url.toString());
        if (!res.ok) return;
        const raw = await res.json();
        const { rows, hasMoreOlder } = parseDmMessagesPayload(raw);
        if (rows.length === 0) {
          setDmMetaBySlug((prev) => ({ ...prev, [slug]: { hasMoreOlder: false } }));
          return;
        }
        const olderMapped = mapRowsToMessages(slug, rows);
        setMessagesBySlug((prev) => {
          const cur = prev[slug] || [];
          const byId = new Map<number, DmMessage>();
          for (const m of olderMapped) byId.set(m.id, m);
          for (const m of cur) byId.set(m.id, m);
          const merged = Array.from(byId.values()).sort((a, b) => a.id - b.id);
          return { ...prev, [slug]: merged };
        });
        setDmMetaBySlug((prev) => ({ ...prev, [slug]: { hasMoreOlder } }));
      } catch {
        // ignore
      } finally {
        setLoadingOlderDmSlug((s) => (s === slug ? null : s));
      }
    },
    [conversations, currentAgentId, messagesBySlug, dmMetaBySlug, mapRowsToMessages],
  );

  const fetchDmMessagesSince = useCallback(
    async (slug: string, sinceIso: string) => {
      if (!currentAgentId) return;
      const conversation = conversations.find((c) => c.slug === slug);
      if (!conversation) return;
      try {
        const url = new URL(`${API_BASE}/api/internal-dm/conversations/${conversation.id}/messages`);
        url.searchParams.set('agent_id', String(Number(currentAgentId)));
        url.searchParams.set('since', sinceIso);
        const res = await fetch(url.toString());
        if (!res.ok) return;
        const raw = await res.json();
        const { rows } = parseDmMessagesPayload(raw);
        if (rows.length === 0) return;
        const chunk = mapRowsToMessages(slug, rows);
        setMessagesBySlug((prev) => {
          const cur = prev[slug] || [];
          const byId = new Map<number, DmMessage>();
          for (const m of cur) byId.set(m.id, m);
          for (const m of chunk) byId.set(m.id, m);
          return { ...prev, [slug]: Array.from(byId.values()).sort((a, b) => a.id - b.id) };
        });
      } catch {
        // ignore
      }
    },
    [conversations, currentAgentId, mapRowsToMessages],
  );

  const mergeIncomingDmMessage = useCallback(
    (slug: string, row: { id: number; sender_agent_id: number; content: string; created_at: string }) => {
      setMessagesBySlug((prev) => {
        const cur = prev[slug] || [];
        if (cur.some((m) => m.id === row.id)) return prev;
        const conv = conversations.find((c) => c.slug === slug);
        const peerName = conv?.name || 'Agent';
        const msg: DmMessage = {
          id: row.id,
          senderAgentId: String(row.sender_agent_id),
          senderName: String(row.sender_agent_id) === String(currentAgentId) ? 'You' : peerName,
          content: row.content,
          createdAt: row.created_at,
        };
        return { ...prev, [slug]: [...cur, msg].sort((a, b) => a.id - b.id) };
      });
      setConversations((prev) =>
        prev
          .map((c) => (c.slug === slug ? { ...c, lastMessageAt: row.created_at } : c))
          .sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime()),
      );
    },
    [conversations, currentAgentId],
  );

  const dmHasMoreOlder = useCallback(
    (slug: string) => dmMetaBySlug[slug]?.hasMoreOlder ?? false,
    [dmMetaBySlug],
  );

  const reportDmUnread = useCallback((slug: string) => {
    setDmUnreadBySlug((prev) => {
      const next = { ...prev, [slug]: (prev[slug] ?? 0) + 1 };
      writeDmUnreadMap(next);
      return next;
    });
  }, []);

  const clearDmUnread = useCallback((slug: string) => {
    setDmUnreadBySlug((prev) => {
      const next = { ...prev };
      if (next[slug]) delete next[slug];
      writeDmUnreadMap(next);
      return next;
    });
  }, []);

  const getDmUnreadCount = useCallback((slug: string) => dmUnreadBySlug[slug] ?? 0, [dmUnreadBySlug]);

  const sendMessageBySlug = useCallback(
    async (slug: string, content: string) => {
      if (!currentAgentId) return;
      const conversation = conversations.find((c) => c.slug === slug);
      if (!conversation) return;
      try {
        const res = await fetch(`${API_BASE}/api/internal-dm/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversation_id: Number(conversation.id),
            sender_agent_id: Number(currentAgentId),
            content,
          }),
        });
        if (!res.ok) return;
        const row = (await res.json()) as {
          id: number;
          sender_agent_id: number;
          content: string;
          created_at: string;
        };
        setMessagesBySlug((prev) => {
          const list = prev[slug] || [];
          if (list.some((m) => m.id === row.id)) return prev;
          return {
            ...prev,
            [slug]: [
              ...list,
              {
                id: row.id,
                senderAgentId: String(row.sender_agent_id),
                senderName: 'You',
                content: row.content,
                createdAt: row.created_at,
              },
            ].sort((a, b) => a.id - b.id),
          };
        });
        setConversations((prev) =>
          prev
            .map((c) => (c.slug === slug ? { ...c, lastMessageAt: row.created_at } : c))
            .sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime()),
        );
        const meName = getCurrentAgent()?.name || 'Agent';
        const peer = conversations.find((c) => c.slug === slug);
        if (peer?.peerAgentId) {
          notifications.addNotification({
            type: 'personal_message',
            message: `${meName} sent you a direct message`,
            description: row.content,
            fromAgentId: currentAgentId,
            toAgentId: peer.peerAgentId,
          });
        }
      } catch {
        // ignore
      }
    },
    [conversations, currentAgentId, getCurrentAgent, notifications],
  );

  const getMessagesBySlug = useCallback((slug: string) => messagesBySlug[slug] || [], [messagesBySlug]);
  const getConversations = useCallback(() => conversations, [conversations]);

  return (
    <DmChatsContext.Provider
      value={{
        conversations,
        addOrUpdateConversation,
        removeConversation,
        getConversationBySlug,
        getMessagesBySlug,
        loadInitialDmThread,
        loadMessagesBySlug: loadInitialDmThread,
        loadOlderDmMessages,
        fetchDmMessagesSince,
        mergeIncomingDmMessage,
        dmHasMoreOlder,
        sendMessageBySlug,
        getConversations,
        refreshConversations,
        isDmListLoading,
        loadingDmSlug,
        loadingOlderDmSlug,
        getDmUnreadCount,
        reportDmUnread,
        clearDmUnread,
      }}
    >
      {children}
    </DmChatsContext.Provider>
  );
}

export function useDmChats() {
  const context = useContext(DmChatsContext);
  if (context === undefined) {
    return {
      conversations: [] as DmConversation[],
      addOrUpdateConversation: async () => {},
      removeConversation: () => {},
      getConversationBySlug: (_slug: string) => undefined,
      getMessagesBySlug: (_slug: string) => [] as DmMessage[],
      loadInitialDmThread: async (_slug: string) => {},
      loadMessagesBySlug: async (_slug: string) => {},
      loadOlderDmMessages: async (_slug: string) => {},
      fetchDmMessagesSince: async (_slug: string, _since: string) => {},
      mergeIncomingDmMessage: (_slug: string, _row: { id: number; sender_agent_id: number; content: string; created_at: string }) => {},
      dmHasMoreOlder: (_slug: string) => false,
      sendMessageBySlug: async (_slug: string, _content: string) => {},
      getConversations: () => [] as DmConversation[],
      refreshConversations: async () => {},
      isDmListLoading: false,
      loadingDmSlug: null,
      loadingOlderDmSlug: null,
      getDmUnreadCount: (_slug: string) => 0,
      reportDmUnread: (_slug: string) => {},
      clearDmUnread: (_slug: string) => {},
    };
  }
  return context;
}
