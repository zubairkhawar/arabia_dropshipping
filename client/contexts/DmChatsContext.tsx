'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { useAgents } from '@/contexts/AgentsContext';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const TENANT_ID = 1;

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
  loadMessagesBySlug: (slug: string) => Promise<void>;
  sendMessageBySlug: (slug: string, content: string) => Promise<void>;
  getConversations: () => DmConversation[];
  refreshConversations: () => Promise<void>;
}

const DmChatsContext = createContext<DmChatsContextType | undefined>(undefined);

export function DmChatsProvider({ children }: { children: ReactNode }) {
  const { getCurrentAgent } = useAgents();
  const currentAgentId = getCurrentAgent()?.id ?? null;
  const [conversations, setConversations] = useState<DmConversation[]>([]);
  const [messagesBySlug, setMessagesBySlug] = useState<Record<string, DmMessage[]>>({});

  const refreshConversations = useCallback(async () => {
    if (!currentAgentId) {
      setConversations([]);
      setMessagesBySlug({});
      return;
    }
    try {
      const url = new URL(`${API_BASE}/api/internal-dm/conversations`);
      url.searchParams.set('tenant_id', String(TENANT_ID));
      url.searchParams.set('agent_id', String(Number(currentAgentId)));
      const res = await fetch(url.toString());
      if (!res.ok) return;
      const rows = (await res.json()) as Array<{
        id: number;
        peer: { agent_id: number; name: string };
        last_message_at: string | null;
      }>;
      const mapped: DmConversation[] = rows.map((row) => {
        const name = row.peer.name || `Agent ${row.peer.agent_id}`;
        const slug = name
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
    } catch {
      // ignore network errors
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
    setConversations((prev) => {
      return prev.filter((c) => c.slug !== slug);
    });
    setMessagesBySlug((prev) => {
      const next = { ...prev };
      delete next[slug];
      return next;
    });
  }, []);

  const getConversationBySlug = useCallback(
    (slug: string) => conversations.find((c) => c.slug === slug),
    [conversations],
  );

  const loadMessagesBySlug = useCallback(async (slug: string) => {
    if (!currentAgentId) return;
    const conversation = conversations.find((c) => c.slug === slug);
    if (!conversation) return;
    try {
      const url = new URL(`${API_BASE}/api/internal-dm/conversations/${conversation.id}/messages`);
      url.searchParams.set('agent_id', String(Number(currentAgentId)));
      const res = await fetch(url.toString());
      if (!res.ok) return;
      const rows = (await res.json()) as Array<{
        id: number;
        sender_agent_id: number;
        content: string;
        created_at: string;
      }>;
      const mapped: DmMessage[] = rows.map((row) => ({
        id: row.id,
        senderAgentId: String(row.sender_agent_id),
        senderName:
          String(row.sender_agent_id) === currentAgentId
            ? 'You'
            : (conversations.find((c) => c.id === conversation.id)?.name || 'Agent'),
        content: row.content,
        createdAt: row.created_at,
      }));
      setMessagesBySlug((prev) => ({ ...prev, [slug]: mapped }));
    } catch {
      // ignore
    }
  }, [conversations, currentAgentId]);

  const sendMessageBySlug = useCallback(async (slug: string, content: string) => {
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
      setMessagesBySlug((prev) => ({
        ...prev,
        [slug]: [
          ...(prev[slug] || []),
          {
            id: row.id,
            senderAgentId: String(row.sender_agent_id),
            senderName: 'You',
            content: row.content,
            createdAt: row.created_at,
          },
        ],
      }));
      setConversations((prev) =>
        prev
          .map((c) => (c.slug === slug ? { ...c, lastMessageAt: row.created_at } : c))
          .sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime()),
      );
    } catch {
      // ignore
    }
  }, [conversations, currentAgentId]);

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
        loadMessagesBySlug,
        sendMessageBySlug,
        getConversations,
        refreshConversations,
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
      loadMessagesBySlug: async (_slug: string) => {},
      sendMessageBySlug: async (_slug: string, _content: string) => {},
      getConversations: () => [] as DmConversation[],
      refreshConversations: async () => {},
    };
  }
  return context;
}
