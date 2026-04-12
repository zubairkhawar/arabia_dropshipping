'use client';

import React, { createContext, useContext, useState, useCallback, ReactNode, useEffect, useRef } from 'react';
import { useAgents } from '@/contexts/AgentsContext';
import { useTenantTimezone } from '@/contexts/TenantTimezoneContext';
import { usePathname } from 'next/navigation';
import { useAgentPortalRealtime } from '@/contexts/AgentPortalRealtimeContext';
import { formatConversationListTime, formatTime12hInZone } from '@/lib/tenant-time';
import {
  readAuthAgentId,
  readLastInboxConversationId,
  writeLastInboxConversationId,
  writeInboxLastReadEntry,
} from '@/lib/agent-session-storage';

export type ConversationStatus = 'active' | 'resolved' | 'pending' | 'transferred';

export interface InboxConversation {
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
  handlerAgentId?: string;
  closedAt?: string;
  isNewLead?: boolean;
  reopenedAt?: string;
  transferredToAgentName?: string;
  transferredFromAgentName?: string;
  transferredAt?: string;
}

export interface InboxMessage {
  id: number;
  content: string;
  sender: 'customer' | 'agent' | 'ai';
  senderName: string;
  timestamp: string;
  sentAt?: string;
  replyToMessageId?: number;
  replyTo?: { id: number; senderName: string; content: string };
  editedAt?: string;
  deletedForEveryone?: boolean;
  messageStatus?: { sent: boolean; delivered: boolean; read: boolean };
  sendFailed?: boolean;
  /** Stored server-side (object_key, type); omit media_url — API adds signed URL when loading. */
  messageMetadata?: Record<string, unknown> | null;
  attachment?: { type: 'photo' | 'voice' | 'file'; name: string; url: string; durationSeconds?: number };
  reactions?: Array<{ emoji: string; userId: string; userName: string; reactedAt: string }>;
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
  patchInboxMessage: (convId: number, messageId: number, patch: Partial<InboxMessage>) => void;
  removeInboxMessage: (convId: number, messageId: number) => void;
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
  customer_phone?: string | null;
  last_message?: string | null;
  last_activity_at?: string | null;
  channel: 'whatsapp' | 'web' | 'portal';
  status: string;
  agent_id?: number | null;
  unread_count?: number;
  is_new_customer?: boolean;
  transfer_from_agent_id?: number | null;
  transfer_from_agent_name?: string | null;
  transfer_to_agent_id?: number | null;
  transfer_to_agent_name?: string | null;
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
    reply_to_message_id?: number | null;
    edited_at?: string | null;
    deleted_for_everyone_at?: string | null;
    reply_preview?: { id: number; sender_type: string; content: string };
    status?: { sent: boolean; delivered: boolean; read: boolean };
    message_metadata?: Record<string, unknown> | null;
  }>;
  has_more_older?: boolean;
}

export function inboxMetaToAttachment(meta: unknown): InboxMessage['attachment'] | undefined {
  if (!meta || typeof meta !== 'object') return undefined;
  const o = meta as Record<string, unknown>;
  const url = typeof o.media_url === 'string' ? o.media_url : undefined;
  if (!url) return undefined;
  if (o.type === 'image') return { type: 'photo', name: 'Image', url };
  if (o.type === 'voice')
    return { type: 'voice', name: 'Voice', url, durationSeconds: Number(o.duration_seconds) || 0 };
  if (o.type === 'file') return { type: 'file', name: String(o.filename || 'File'), url };
  return undefined;
}

function apiMessageToInbox(
  m: ConversationDetailsApi['messages'][number],
  timeZone: string,
): InboxMessage {
  const st = m.sender_type;
  const senderName = st === 'agent' ? 'You' : st === 'customer' ? 'Customer' : 'AI';
  const rp = m.reply_preview;
  let content = m.content;
  let attachment = inboxMetaToAttachment(m.message_metadata);
  if (!attachment && content.startsWith('data:image')) {
    attachment = { type: 'photo', name: 'Image', url: content };
    content = '';
  } else if (!attachment && (content.startsWith('data:audio') || content.startsWith('data:video'))) {
    attachment = { type: 'voice', name: 'Voice', url: content };
    content = '';
  }
  const meta = (m.message_metadata ?? undefined) as Record<string, unknown> | undefined;
  const reactionsRaw = meta?.reactions;
  const reactions = Array.isArray(reactionsRaw)
    ? reactionsRaw.filter(
        (r): r is { emoji: string; userId: string; userName: string; reactedAt: string } =>
          Boolean(
            r &&
              typeof r === 'object' &&
              typeof (r as { emoji?: unknown }).emoji === 'string' &&
              typeof (r as { userId?: unknown }).userId === 'string' &&
              typeof (r as { userName?: unknown }).userName === 'string' &&
              typeof (r as { reactedAt?: unknown }).reactedAt === 'string',
          ),
      )
    : undefined;
  return {
    id: m.id,
    content,
    sender: st,
    senderName,
    timestamp: formatTime12hInZone(new Date(m.created_at), timeZone),
    sentAt: m.created_at,
    replyToMessageId: m.reply_to_message_id ?? undefined,
    editedAt: m.edited_at ?? undefined,
    deletedForEveryone: Boolean(m.deleted_for_everyone_at),
    messageStatus: m.status,
    messageMetadata: m.message_metadata ?? undefined,
    attachment,
    reactions,
    replyTo: rp
      ? {
          id: rp.id,
          senderName: rp.sender_type === 'agent' ? 'You' : rp.sender_type === 'customer' ? 'Customer' : 'AI',
          content: rp.content,
        }
      : undefined,
  };
}

function toConversationStatus(status: string): ConversationStatus {
  if (status === 'closed' || status === 'resolved') return 'resolved';
  if (status === 'transferred') return 'transferred';
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
  const { timeZone } = useTenantTimezone();
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
      const aid = currentAgentId ?? readAuthAgentId();
      const handlerAgentId = c.agent_id != null ? String(c.agent_id) : undefined;
      const handlerName =
        handlerAgentId != null ? agents.find((a) => a.id === handlerAgentId)?.name : undefined;
      // Show as "transferred" for the prior handler when they no longer own the thread.
      // (Do not require transfer_to !== agent_id — after a successful handoff both match the new assignee.)
      const transferredOut =
        aid != null &&
        c.transfer_from_agent_id != null &&
        Number(c.transfer_from_agent_id) === Number(aid) &&
        (c.agent_id == null || Number(c.agent_id) !== Number(aid));
      return {
        id: c.id,
        customerName: c.customer_name || `Customer #${c.customer_id}`,
        customerPhone: c.customer_phone || undefined,
        customerId: `#${c.customer_id}`,
        lastMessage: c.last_message || '',
        lastActivityAt: formatConversationListTime(c.last_activity_at, timeZone),
        unread: typeof c.unread_count === 'number' ? c.unread_count : 0,
        channel: c.channel,
        status: transferredOut ? 'transferred' : toConversationStatus(c.status),
        handlerType: handlerAgentId ? 'agent' : 'ai',
        handlerName,
        handlerAgentId,
        isNewLead: Boolean(c.is_new_customer),
        transferredToAgentName: c.transfer_to_agent_name ?? undefined,
        transferredFromAgentName: c.transfer_from_agent_name ?? undefined,
        transferredAt: transferredOut ? formatConversationListTime(c.last_activity_at, timeZone) : undefined,
      };
    },
    [agents, currentAgentId, timeZone],
  );

  const fetchConversationRowsFromApi = useCallback(async (): Promise<ConversationSummaryApi[]> => {
    const aid = isAgentPortal ? (currentAgentId ?? readAuthAgentId()) : null;
    if (isAgentPortal && !aid) return [];
    const url = new URL(`${API_BASE}/api/messaging/conversations`);
    url.searchParams.set('tenant_id', String(TENANT_ID));
    if (isAgentPortal && aid) {
      url.searchParams.set('agent_id', String(Number(aid)));
      url.searchParams.set('include_transferred_out_for_agent_id', String(Number(aid)));
    }
    const res = await fetch(url.toString());
    if (!res.ok) return [];
    const rows = (await res.json()) as ConversationSummaryApi[];
    if (isAgentPortal) return rows;
    // Admin: show assigned chats plus active bot-queue (WhatsApp/web) so handoffs and stuck flows are visible
    return rows.filter(
      (c) =>
        c.agent_id != null ||
        ((c.channel === 'whatsapp' || c.channel === 'web') && c.status === 'active'),
    );
  }, [currentAgentId, isAgentPortal]);

  const mapDetailToMessages = useCallback(
    (data: ConversationDetailsApi): InboxMessage[] => {
      return data.messages.map((m) => apiMessageToInbox(m, timeZone));
    },
    [timeZone],
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
        const res = await fetch(url.toString(), { headers: authJsonHeaders() });
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
        if (mapped.length > 0) {
          const maxId = Math.max(...mapped.map((m) => m.id));
          void syncInboxReadState(convId, maxId);
        }
      } catch {
        setMessagesByConvId((prev) => ({ ...prev, [convId]: [] }));
        setInboxMetaByConvId((prev) => ({ ...prev, [convId]: { hasMoreOlder: false } }));
      } finally {
        setLoadingConversationId((id) => (id === convId ? null : id));
      }
    },
    [mapDetailToMessages, syncInboxReadState],
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
        const res = await fetch(url.toString(), { headers: authJsonHeaders() });
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

  useEffect(() => {
    return subscribe((msg) => {
      const convId = msg.conversation_id;
      if (msg.type === 'inbox_message') {
        if (typeof convId !== 'number') return;
        const raw = msg.message;
        if (!raw || typeof raw !== 'object') return;
        const row = raw as ConversationDetailsApi['messages'][number];
        if (!row.id) return;
        const im = apiMessageToInbox(row, timeZone);
        const id = im.id;
        const viewing = selectedIdRef.current === convId;
        if (viewing) {
          setMessagesByConvId((prev) => {
            const cur = prev[convId] || [];
            if (cur.some((x) => x.id === id)) return prev;
            return { ...prev, [convId]: [...cur, im].sort((a, b) => a.id - b.id) };
          });
          void syncInboxReadState(convId, id);
        } else {
          setConversations((prev) => {
            const exists = prev.some((c) => c.id === convId);
            if (!exists) {
              queueMicrotask(() => {
                void refreshConversations();
              });
              return prev;
            }
            return prev.map((c) =>
              c.id === convId
                ? {
                    ...c,
                    unread: c.unread + 1,
                    lastMessage: im.content,
                    lastActivityAt: 'Just now',
                  }
                : c,
            );
          });
        }
        return;
      }
      if (msg.type === 'inbox_message_updated' && typeof convId === 'number') {
        const raw = msg.message;
        if (!raw || typeof raw !== 'object') return;
        const row = raw as ConversationDetailsApi['messages'][number];
        const im = apiMessageToInbox(row, timeZone);
        setMessagesByConvId((prev) => {
          const cur = prev[convId] || [];
          const idx = cur.findIndex((x) => x.id === im.id);
          if (idx < 0) return prev;
          const next = [...cur];
          next[idx] = im;
          return { ...prev, [convId]: next };
        });
        return;
      }
      if (msg.type === 'MESSAGE_DELETED' && typeof convId === 'number') {
        const mid = Number(msg.message_id);
        if (!Number.isFinite(mid)) return;
        setMessagesByConvId((prev) => {
          const cur = prev[convId] || [];
          return {
            ...prev,
            [convId]: cur.map((x) =>
              x.id === mid
                ? { ...x, content: '[Message deleted]', deletedForEveryone: true }
                : x,
            ),
          };
        });
        return;
      }
      if (msg.type === 'inbox_conversation_refresh') {
        queueMicrotask(() => {
          void refreshConversations();
        });
        return;
      }
      if (msg.type === 'conversation_transferred') {
        queueMicrotask(() => {
          void refreshConversations();
        });
        return;
      }
      if (msg.type === 'portal_connected') {
        queueMicrotask(() => {
          void refreshConversations();
        });
        return;
      }
    });
  }, [subscribe, syncInboxReadState, timeZone, refreshConversations]);

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
      listUrl.searchParams.set('include_transferred_out_for_agent_id', String(Number(aid)));

      try {
        const [rowsRaw, detailData] = await Promise.all([
          fetch(listUrl.toString()).then(async (r) => (r.ok ? r.json() : [])),
          lastId != null
            ? fetch(`${API_BASE}/api/messaging/conversations/${lastId}?limit=50`, {
                headers: authJsonHeaders(),
              }).then(async (r) => (r.ok ? r.json() : null))
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
          if (mappedMsgs.length > 0) {
            const maxId = Math.max(...mappedMsgs.map((m) => m.id));
            void syncInboxReadState(convId, maxId);
          }
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
  }, [
    isAgentPortal,
    currentAgentId,
    mapConversation,
    fetchConversationRowsFromApi,
    mapDetailToMessages,
    syncInboxReadState,
  ]);

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

  const closeConversation = useCallback(
    (convId: number) => {
    const now = new Date();
    const closedAt = `${formatTime12hInZone(now, timeZone)}, ${now.toLocaleDateString('en-US', {
      timeZone,
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })}`;
    setConversations((prev) =>
      prev.map((c) => (c.id === convId ? { ...c, status: 'resolved', closedAt, unread: 0 } : c)),
    );
    void fetch(`${API_BASE}/api/messaging/conversations/${convId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'closed' }),
    });
  },
    [timeZone],
  );

  const reopenConversation = useCallback(
    (convId: number) => {
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
      timestamp: formatTime12hInZone(now, timeZone),
      sentAt: now.toISOString(),
    };
    setMessagesByConvId((prev) => ({
      ...prev,
      [convId]: [...(prev[convId] ?? []), systemMsg],
    }));
  },
    [timeZone],
  );

  const transferConversation = useCallback((convId: number, toAgentId: string, toAgentName: string) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId
          ? {
              ...c,
              status: 'transferred',
              handlerType: 'agent',
              handlerAgentId: toAgentId,
              handlerName: toAgentName,
              transferredToAgentName: toAgentName,
              transferredAt: 'Just now',
              lastMessage: 'Conversation transferred.',
              lastActivityAt: 'Just now',
            }
          : c,
      ),
    );
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    void fetch(`${API_BASE}/api/routing/transfer`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        conversation_id: convId,
        target_agent_id: Number(toAgentId),
      }),
    });
  }, []);

  const sendConversationToAI = useCallback((convId: number) => {
    const now = new Date();
    const closedAt = `${formatTime12hInZone(now, timeZone)}, ${now.toLocaleDateString('en-US', {
      timeZone,
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })}`;
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId
          ? {
              ...c,
              handlerType: 'ai',
              handlerName: undefined,
              handlerAgentId: undefined,
              status: 'resolved',
              closedAt,
              unread: 0,
              lastMessage: 'Conversation transferred to Arabia Dropbot.',
              lastActivityAt: 'Just now',
            }
          : c,
      ),
    );
    void fetch(`${API_BASE}/api/messaging/conversations/${convId}/send-to-ai`, {
      method: 'POST',
    });
  }, [timeZone]);

  const getMessages = useCallback((convId: number) => messagesByConvId[convId] ?? [], [messagesByConvId]);

  const setMessages = useCallback((convId: number, messages: InboxMessage[]) => {
    setMessagesByConvId((prev) => ({ ...prev, [convId]: messages }));
  }, []);

  const appendMessage = useCallback((convId: number, message: InboxMessage) => {
    setMessagesByConvId((prev) => ({
      ...prev,
      [convId]: [...(prev[convId] ?? []), message],
    }));

    const hasText = typeof message.content === 'string' && message.content.trim();
    const meta = message.messageMetadata;
    const hasMediaMeta =
      meta &&
      typeof meta === 'object' &&
      typeof (meta as Record<string, unknown>).object_key === 'string';
    if (hasText || hasMediaMeta) {
      const body: Record<string, unknown> = {
        conversation_id: convId,
        content: typeof message.content === 'string' ? message.content : '',
        sender_type: message.sender,
        channel: 'whatsapp',
      };
      if (hasMediaMeta) body.message_metadata = meta;
      const rt = message.replyToMessageId;
      if (typeof rt === 'number' && rt > 0) body.reply_to_message_id = rt;
      void fetch(`${API_BASE}/api/messaging/messages`, {
        method: 'POST',
        headers: authJsonHeaders(),
        body: JSON.stringify(body),
      }).then(async (res) => {
        if (!res.ok) {
          setMessagesByConvId((prev) => {
            const cur = prev[convId] || [];
            const idx = cur.findIndex((x) => x.id === message.id);
            if (idx < 0) return prev;
            const next = [...cur];
            next[idx] = { ...next[idx], sendFailed: true };
            return { ...prev, [convId]: next };
          });
          return;
        }
        const saved = (await res.json()) as {
          id: number;
          created_at: string;
          reply_to_message_id?: number | null;
          edited_at?: string | null;
          message_metadata?: Record<string, unknown> | null;
          status?: { sent: boolean; delivered: boolean; read: boolean };
        };
        const serverAtt = inboxMetaToAttachment(saved.message_metadata);
        setMessagesByConvId((prev) => {
          const cur = prev[convId] || [];
          const idx = cur.findIndex((x) => x.id === message.id);
          if (idx < 0) return prev;
          const next = [...cur];
          next[idx] = {
            ...next[idx],
            id: saved.id,
            sentAt: saved.created_at,
            replyToMessageId: saved.reply_to_message_id ?? next[idx].replyToMessageId,
            editedAt: saved.edited_at ?? next[idx].editedAt,
            messageStatus: saved.status ?? { sent: true, delivered: true, read: true },
            messageMetadata: saved.message_metadata ?? next[idx].messageMetadata,
            attachment: serverAtt ?? next[idx].attachment,
          };
          return { ...prev, [convId]: next };
        });
        setConversations((prev) =>
          prev.map((c) =>
            c.id === convId
              ? {
                  ...c,
                  lastMessage: hasText
                    ? String(message.content)
                    : hasMediaMeta
                      ? '[Media]'
                      : c.lastMessage,
                  lastActivityAt: 'Just now',
                  status: c.status === 'resolved' ? 'active' : c.status,
                }
              : c,
          ),
        );
      });
    }
  }, []);

  const patchInboxMessage = useCallback((convId: number, messageId: number, patch: Partial<InboxMessage>) => {
    setMessagesByConvId((prev) => {
      const cur = prev[convId] || [];
      return {
        ...prev,
        [convId]: cur.map((m) => (m.id === messageId ? { ...m, ...patch } : m)),
      };
    });
  }, []);

  const removeInboxMessage = useCallback((convId: number, messageId: number) => {
    setMessagesByConvId((prev) => ({
      ...prev,
      [convId]: (prev[convId] || []).filter((x) => x.id !== messageId),
    }));
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
        patchInboxMessage,
        removeInboxMessage,
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
