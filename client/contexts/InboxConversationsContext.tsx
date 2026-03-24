'use client';

import React, { createContext, useContext, useState, useCallback, ReactNode, useEffect } from 'react';
import { useAgents } from '@/contexts/AgentsContext';
import { usePathname } from 'next/navigation';

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
}

const InboxConversationsContext = createContext<InboxConversationsContextType | null>(null);

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const TENANT_ID = 1;

interface ConversationSummaryApi {
  id: number;
  customer_id: number;
  customer_name?: string | null;
  last_message?: string | null;
  last_activity_at?: string | null;
  channel: 'whatsapp' | 'web' | 'portal';
  status: string;
  agent_id?: number | null;
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

export function InboxConversationsProvider({ children }: { children: ReactNode }) {
  const { agents, currentAgentId } = useAgents();
  const pathname = usePathname();
  const isAgentPortal = pathname?.startsWith('/agent/');
  const [conversations, setConversations] = useState<InboxConversation[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [messagesByConvId, setMessagesByConvId] = useState<Record<number, InboxMessage[]>>({});
  const [isLoading, setIsLoading] = useState(true);

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
        unread: 0,
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

  const refreshConversations = useCallback(async () => {
    try {
      const url = new URL(`${API_BASE}/api/messaging/conversations`);
      url.searchParams.set('tenant_id', String(TENANT_ID));
      if (isAgentPortal && currentAgentId) {
        url.searchParams.set('agent_id', String(Number(currentAgentId)));
      }
      const res = await fetch(url.toString());
      if (!res.ok) return;
      const rows = (await res.json()) as ConversationSummaryApi[];
      const mapped = rows.map(mapConversation);
      setConversations(mapped);
      setSelectedId((prev) => {
        if (prev && mapped.some((c) => c.id === prev)) return prev;
        return mapped[0]?.id ?? null;
      });
    } finally {
      setIsLoading(false);
    }
  }, [currentAgentId, isAgentPortal, mapConversation]);

  const loadMessagesForConversation = useCallback(async (convId: number) => {
    try {
      const res = await fetch(`${API_BASE}/api/messaging/conversations/${convId}`);
      if (!res.ok) return;
      const data = (await res.json()) as ConversationDetailsApi;
      const mapped: InboxMessage[] = data.messages.map((m) => ({
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
      setMessagesByConvId((prev) => ({ ...prev, [convId]: mapped }));
    } catch {
      // ignore fetch errors
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  useEffect(() => {
    if (selectedId == null) return;
    if (messagesByConvId[selectedId]) return;
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
      }}
    >
      {children}
    </InboxConversationsContext.Provider>
  );
}

export function useInboxConversations() {
  return useContext(InboxConversationsContext);
}
