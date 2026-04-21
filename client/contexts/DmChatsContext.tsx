'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, useRef, ReactNode } from 'react';
import { useAgents } from '@/contexts/AgentsContext';
import { readAuthAgentId, readLastDmPrefs, writeLastDmPrefs } from '@/lib/agent-session-storage';
import { parseBackendUtcDate } from '@/lib/tenant-time';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const TENANT_ID = 1;
const DM_CONVERSATIONS_REFRESH_MS = 10_000;
const DM_GET_CACHE_TTL_MS = 10_000;
const dmGetCache = new Map<string, { timestamp: number; data: unknown }>();

function dmAuthHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  if (typeof window !== 'undefined') {
    const t = localStorage.getItem('auth_token');
    if (t) h.Authorization = `Bearer ${t}`;
  }
  return h;
}

function dmJsonHeaders(): Record<string, string> {
  return { 'Content-Type': 'application/json', ...dmAuthHeaders() };
}

async function dmGetJsonWithCache(url: string, ttlMs = DM_GET_CACHE_TTL_MS): Promise<unknown> {
  const auth = dmAuthHeaders().Authorization ?? '';
  const key = `${url}|${auth}`;
  const now = Date.now();
  const cached = dmGetCache.get(key);
  if (cached && now - cached.timestamp < ttlMs) {
    return cached.data;
  }
  const res = await fetch(url, { headers: dmAuthHeaders() });
  if (!res.ok) {
    throw new Error(`GET failed: ${res.status}`);
  }
  const data = (await res.json()) as unknown;
  dmGetCache.set(key, { timestamp: now, data });
  return data;
}

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

type DmApiMessageRow = {
  id: number;
  sender_agent_id: number;
  content: string;
  created_at: string;
  reply_to_message_id?: number | null;
  edited_at?: string | null;
  deleted_for_everyone_at?: string | null;
  peer_delivered_at?: string | null;
  peer_read_at?: string | null;
  message_metadata?: Record<string, unknown> | null;
};

function parseDmMessagesPayload(data: unknown): {
  rows: DmApiMessageRow[];
  hasMoreOlder: boolean;
} {
  if (Array.isArray(data)) {
    return { rows: data as DmApiMessageRow[], hasMoreOlder: false };
  }
  if (data && typeof data === 'object' && 'messages' in data) {
    const o = data as { messages: unknown; has_more_older?: boolean };
    const arr = Array.isArray(o.messages) ? o.messages : [];
    return { rows: arr as DmApiMessageRow[], hasMoreOlder: Boolean(o.has_more_older) };
  }
  return { rows: [], hasMoreOlder: false };
}

export interface DmConversation {
  id: string;
  peerAgentId: string;
  slug: string;
  name: string;
  lastMessageAt: string;
  /** Peer profile image from server (user avatar). */
  peerAvatarUrl?: string | null;
}

export interface DmMessage {
  id: number;
  content: string;
  senderAgentId: string;
  senderName: string;
  createdAt: string;
  replyToMessageId?: number;
  editedAt?: string;
  deletedForEveryone?: boolean;
  peerDeliveredAt?: string;
  peerReadAt?: string;
  messageMetadata?: Record<string, unknown> | null;
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
  mergeIncomingDmMessage: (slug: string, row: DmApiMessageRow) => void;
  patchDmMessage: (slug: string, messageId: number, patch: Partial<DmMessage>) => void;
  dmHasMoreOlder: (slug: string) => boolean;
  sendMessageBySlug: (
    slug: string,
    content: string,
    replyToMessageId?: number,
    messageMetadata?: Record<string, unknown>,
  ) => Promise<void>;
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
  const currentAgentId = getCurrentAgent()?.id ?? readAuthAgentId();
  const [conversations, setConversations] = useState<DmConversation[]>([]);
  const [messagesBySlug, setMessagesBySlug] = useState<Record<string, DmMessage[]>>({});
  const [dmMetaBySlug, setDmMetaBySlug] = useState<Record<string, { hasMoreOlder: boolean }>>({});
  const [dmUnreadBySlug, setDmUnreadBySlug] = useState<Record<string, number>>(() => readDmUnreadMap());
  const [isDmListLoading, setIsDmListLoading] = useState(true);
  const [loadingDmSlug, setLoadingDmSlug] = useState<string | null>(null);
  const [loadingOlderDmSlug, setLoadingOlderDmSlug] = useState<string | null>(null);
  const lastSeenConversationTsRef = useRef<Record<string, string>>({});
  const hasLoadedDmListRef = useRef(false);

  const mapRowsToMessages = useCallback(
    (slug: string, rows: DmApiMessageRow[]): DmMessage[] => {
      const conv = conversations.find((c) => c.slug === slug);
      const peerName = conv?.name || 'Agent';
      return rows.map((row) => ({
        id: row.id,
        senderAgentId: String(row.sender_agent_id),
        senderName: String(row.sender_agent_id) === String(currentAgentId) ? 'You' : peerName,
        content: row.content,
        createdAt: row.created_at,
        replyToMessageId: row.reply_to_message_id ?? undefined,
        editedAt: row.edited_at ?? undefined,
        deletedForEveryone: Boolean(row.deleted_for_everyone_at),
        peerDeliveredAt: row.peer_delivered_at ?? undefined,
        peerReadAt: row.peer_read_at ?? undefined,
        messageMetadata: row.message_metadata ?? undefined,
      }));
    },
    [conversations, currentAgentId],
  );

  const refreshConversations = useCallback(async () => {
    if (!currentAgentId) {
      setConversations([]);
      setMessagesBySlug({});
      setDmMetaBySlug({});
      lastSeenConversationTsRef.current = {};
      hasLoadedDmListRef.current = false;
      setIsDmListLoading(false);
      return;
    }
    // Only show full-list skeleton on first load; background refreshes should be silent.
    if (!hasLoadedDmListRef.current) setIsDmListLoading(true);
    const last = readLastDmPrefs();
    const listUrl = new URL(`${API_BASE}/api/internal-dm/conversations`);
    listUrl.searchParams.set('tenant_id', String(TENANT_ID));
    listUrl.searchParams.set('agent_id', String(Number(currentAgentId)));

    try {
      const lastMessagesUrl = last
        ? `${API_BASE}/api/internal-dm/conversations/${last.conversationId}/messages?agent_id=${encodeURIComponent(
            String(Number(currentAgentId)),
          )}&limit=50`
        : null;
      const [rowsRaw, lastMessagesRaw] = await Promise.all([
        dmGetJsonWithCache(listUrl.toString()),
        lastMessagesUrl ? dmGetJsonWithCache(lastMessagesUrl) : Promise.resolve(null),
      ]);
      const rows = rowsRaw as Array<{
        id: number;
        peer: { agent_id: number; name: string; avatar_url?: string | null };
        last_message_at: string | null;
      }>;
      const mapped: DmConversation[] = rows.map((row) => {
        const name = row.peer.name || `Agent ${row.peer.agent_id}`;
        const slug =
          name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '') || String(row.peer.agent_id);
        const peerAvatarUrl =
          row.peer.avatar_url != null && String(row.peer.avatar_url).trim() !== ''
            ? String(row.peer.avatar_url).trim()
            : null;
        return {
          id: String(row.id),
          peerAgentId: String(row.peer.agent_id),
          slug,
          name,
          lastMessageAt: row.last_message_at || new Date().toISOString(),
          peerAvatarUrl,
        };
      });
      setConversations(mapped);
      const prevSeen = lastSeenConversationTsRef.current;
      const nextSeen: Record<string, string> = { ...prevSeen };
      const changed = mapped.filter((c) => {
        const prevTs = prevSeen[c.slug];
        if (!prevTs) return false;
        return (parseBackendUtcDate(c.lastMessageAt) ?? new Date(c.lastMessageAt)).getTime() > (parseBackendUtcDate(prevTs) ?? new Date(prevTs)).getTime();
      });
      for (const c of mapped) nextSeen[c.slug] = c.lastMessageAt;
      lastSeenConversationTsRef.current = nextSeen;

      if (changed.length > 0) {
        const incrementsBySlug: Record<string, number> = {};
        await Promise.all(
          changed.map(async (c) => {
            const prevTs = prevSeen[c.slug];
            if (!prevTs) return;
            try {
              const url = new URL(`${API_BASE}/api/internal-dm/conversations/${c.id}/messages`);
              url.searchParams.set('agent_id', String(Number(currentAgentId)));
              url.searchParams.set('since', prevTs);
              const res = await fetch(url.toString(), { headers: dmAuthHeaders() });
              if (!res.ok) return;
              const raw = await res.json();
              const { rows: deltaRows } = parseDmMessagesPayload(raw);
              const incomingCount = deltaRows.filter(
                (m) => String(m.sender_agent_id) !== String(currentAgentId),
              ).length;
              if (incomingCount > 0) incrementsBySlug[c.slug] = incomingCount;
            } catch {
              // ignore
            }
          }),
        );
        if (Object.keys(incrementsBySlug).length > 0) {
          setDmUnreadBySlug((prev) => {
            const next = { ...prev };
            for (const [slug, inc] of Object.entries(incrementsBySlug)) {
              next[slug] = (next[slug] ?? 0) + inc;
            }
            writeDmUnreadMap(next);
            return next;
          });
        }
      }

      if (lastMessagesRaw && last) {
        const slugFromList = mapped.find((c) => c.id === last.conversationId)?.slug ?? last.slug;
        const { rows: msgRows, hasMoreOlder } = parseDmMessagesPayload(lastMessagesRaw);
        const peerName =
          mapped.find((c) => c.slug === slugFromList)?.name ||
          'Agent';
        const mappedMsgs: DmMessage[] = msgRows.map((row) => ({
          id: row.id,
          senderAgentId: String(row.sender_agent_id),
          senderName: String(row.sender_agent_id) === String(currentAgentId) ? 'You' : peerName,
          content: row.content,
          createdAt: row.created_at,
          replyToMessageId: row.reply_to_message_id ?? undefined,
          editedAt: row.edited_at ?? undefined,
          deletedForEveryone: Boolean(row.deleted_for_everyone_at),
          peerDeliveredAt: row.peer_delivered_at ?? undefined,
          peerReadAt: row.peer_read_at ?? undefined,
          messageMetadata: row.message_metadata ?? undefined,
        }));
        setMessagesBySlug((prev) => ({ ...prev, [slugFromList]: mappedMsgs }));
        setDmMetaBySlug((prev) => ({ ...prev, [slugFromList]: { hasMoreOlder } }));
        writeLastDmPrefs(last.conversationId, slugFromList);
      }
      hasLoadedDmListRef.current = true;
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
        headers: dmJsonHeaders(),
        body: JSON.stringify({
          tenant_id: TENANT_ID,
          agent_id: Number(currentAgentId),
          peer_agent_id: Number(peerAgentId),
        }),
      });
      if (!res.ok) return;
      const row = (await res.json()) as {
        id: number;
        peer: { agent_id: number; name: string; avatar_url?: string | null };
        last_message_at: string | null;
      };
      const peerAvatarUrl =
        row.peer.avatar_url != null && String(row.peer.avatar_url).trim() !== ''
          ? String(row.peer.avatar_url).trim()
          : null;
      setConversations((prev) => {
        const rest = prev.filter((c) => c.slug !== slug);
        const updated: DmConversation[] = [
          {
            id: String(row.id),
            peerAgentId: String(row.peer.agent_id),
            slug,
            name: row.peer.name || name,
            lastMessageAt: row.last_message_at || new Date().toISOString(),
            peerAvatarUrl,
          },
          ...rest,
        ].sort((a, b) => (parseBackendUtcDate(b.lastMessageAt) ?? new Date(b.lastMessageAt)).getTime() - (parseBackendUtcDate(a.lastMessageAt) ?? new Date(a.lastMessageAt)).getTime());
        return updated;
      });
      lastSeenConversationTsRef.current = {
        ...lastSeenConversationTsRef.current,
        [slug]: row.last_message_at || new Date().toISOString(),
      };
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
    const seen = { ...lastSeenConversationTsRef.current };
    delete seen[slug];
    lastSeenConversationTsRef.current = seen;
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
        const res = await fetch(url.toString(), { headers: dmAuthHeaders() });
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
        const res = await fetch(url.toString(), { headers: dmAuthHeaders() });
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
        const res = await fetch(url.toString(), { headers: dmAuthHeaders() });
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
    (slug: string, row: DmApiMessageRow) => {
      let wasNew = false;
      setMessagesBySlug((prev) => {
        const cur = prev[slug] || [];
        wasNew = !cur.some((m) => m.id === row.id);
        const conv = conversations.find((c) => c.slug === slug);
        const peerName = conv?.name || 'Agent';
        const prevSame = cur.find((m) => m.id === row.id);
        const msg: DmMessage = {
          id: row.id,
          senderAgentId: String(row.sender_agent_id),
          senderName: String(row.sender_agent_id) === String(currentAgentId) ? 'You' : peerName,
          content: row.content,
          createdAt: row.created_at,
          replyToMessageId: row.reply_to_message_id ?? undefined,
          editedAt: row.edited_at ?? undefined,
          deletedForEveryone: Boolean(row.deleted_for_everyone_at),
          peerDeliveredAt: row.peer_delivered_at ?? prevSame?.peerDeliveredAt,
          peerReadAt: row.peer_read_at ?? prevSame?.peerReadAt,
          messageMetadata: row.message_metadata ?? prevSame?.messageMetadata,
        };
        const next = wasNew
          ? [...cur, msg].sort((a, b) => a.id - b.id)
          : cur.map((m) => (m.id === row.id ? msg : m));
        return { ...prev, [slug]: next };
      });
      if (wasNew) {
        setConversations((prev) =>
          prev
            .map((c) => (c.slug === slug ? { ...c, lastMessageAt: row.created_at } : c))
            .sort((a, b) => (parseBackendUtcDate(b.lastMessageAt) ?? new Date(b.lastMessageAt)).getTime() - (parseBackendUtcDate(a.lastMessageAt) ?? new Date(a.lastMessageAt)).getTime()),
        );
        lastSeenConversationTsRef.current = {
          ...lastSeenConversationTsRef.current,
          [slug]: row.created_at,
        };
      }
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
    async (
      slug: string,
      content: string,
      replyToMessageId?: number,
      messageMetadata?: Record<string, unknown>,
    ) => {
      if (!currentAgentId) return;
      const conversation = conversations.find((c) => c.slug === slug);
      if (!conversation) return;
      try {
        const body: Record<string, number | string | Record<string, unknown>> = {
          conversation_id: Number(conversation.id),
          sender_agent_id: Number(currentAgentId),
          content,
        };
        if (messageMetadata && Object.keys(messageMetadata).length > 0) {
          body.message_metadata = messageMetadata;
        }
        if (typeof replyToMessageId === 'number' && replyToMessageId > 0) {
          body.reply_to_message_id = replyToMessageId;
        }
        const res = await fetch(`${API_BASE}/api/internal-dm/messages`, {
          method: 'POST',
          headers: dmJsonHeaders(),
          body: JSON.stringify(body),
        });
        if (!res.ok) return;
        const row = (await res.json()) as DmApiMessageRow;
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
                replyToMessageId: row.reply_to_message_id ?? undefined,
                editedAt: row.edited_at ?? undefined,
                deletedForEveryone: Boolean(row.deleted_for_everyone_at),
                peerDeliveredAt: row.peer_delivered_at ?? undefined,
                peerReadAt: row.peer_read_at ?? undefined,
                messageMetadata: row.message_metadata ?? undefined,
              },
            ].sort((a, b) => a.id - b.id),
          };
        });
        setConversations((prev) =>
          prev
            .map((c) => (c.slug === slug ? { ...c, lastMessageAt: row.created_at } : c))
            .sort((a, b) => (parseBackendUtcDate(b.lastMessageAt) ?? new Date(b.lastMessageAt)).getTime() - (parseBackendUtcDate(a.lastMessageAt) ?? new Date(a.lastMessageAt)).getTime()),
        );
        lastSeenConversationTsRef.current = {
          ...lastSeenConversationTsRef.current,
          [slug]: row.created_at,
        };
      } catch {
        // ignore
      }
    },
    [conversations, currentAgentId, getCurrentAgent],
  );

  const patchDmMessage = useCallback((slug: string, messageId: number, patch: Partial<DmMessage>) => {
    setMessagesBySlug((prev) => {
      const cur = prev[slug] || [];
      return {
        ...prev,
        [slug]: cur.map((m) => (m.id === messageId ? { ...m, ...patch } : m)),
      };
    });
  }, []);

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
        patchDmMessage,
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
      mergeIncomingDmMessage: (_slug: string, _row: DmApiMessageRow) => {},
      patchDmMessage: (_slug: string, _messageId: number, _patch: Partial<DmMessage>) => {},
      dmHasMoreOlder: (_slug: string) => false,
      sendMessageBySlug: async (_slug: string, _content: string, _replyTo?: number, _meta?: Record<string, unknown>) => {},
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
