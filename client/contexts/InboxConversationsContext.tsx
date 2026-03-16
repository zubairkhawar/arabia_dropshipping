'use client';

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';

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
  /** When set, conversation was closed and then customer messaged again; now back in live. Same agent. */
  reopenedAt?: string;
}

/** Minimal message shape for per-conversation history (so reopened chats show previous thread). */
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
  markAgentReplied: (convId: number) => void;
  closeConversation: (convId: number) => void;
  reopenConversation: (convId: number) => void;
  transferConversation: (convId: number, toAgentId: string, toAgentName: string, description?: string) => void;
  getMessages: (convId: number) => InboxMessage[];
  setMessages: (convId: number, messages: InboxMessage[]) => void;
  appendMessage: (convId: number, message: InboxMessage) => void;
}

const InboxConversationsContext = createContext<InboxConversationsContextType | null>(null);

const initialConversations: InboxConversation[] = [
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

export function InboxConversationsProvider({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<InboxConversation[]>(initialConversations);
  const [selectedId, setSelectedId] = useState<number | null>(1);
  const [messagesByConvId, setMessagesByConvId] = useState<Record<number, InboxMessage[]>>({});

  const markAgentReplied = useCallback((convId: number) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId ? { ...c, isNewLead: false, unread: 0 } : c
      )
    );
  }, []);

  const closeConversation = useCallback((convId: number) => {
    const now = new Date();
    const closedAt = now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) + ', ' + now.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId ? { ...c, status: 'resolved' as const, closedAt, unread: 0 } : c
      )
    );
  }, []);

  const reopenConversation = useCallback((convId: number) => {
    const now = new Date();
    const reopenedAt = now.toISOString();
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId
          ? {
              ...c,
              status: 'active' as const,
              isNewLead: false,
              unread: 1,
              reopenedAt,
              lastMessage: 'Customer has messaged again.',
              lastActivityAt: 'Just now',
            }
          : c
      )
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
              handlerType: 'agent' as const,
              handlerAgentId: toAgentId,
              handlerName: toAgentName,
              lastMessage: 'Conversation transferred.',
              lastActivityAt: 'Just now',
            }
          : c
      )
    );
  }, []);

  const getMessages = useCallback(
    (convId: number) => messagesByConvId[convId] ?? [],
    [messagesByConvId]
  );

  const setMessages = useCallback((convId: number, messages: InboxMessage[]) => {
    setMessagesByConvId((prev) => ({ ...prev, [convId]: messages }));
  }, []);

  const appendMessage = useCallback((convId: number, message: InboxMessage) => {
    setMessagesByConvId((prev) => ({
      ...prev,
      [convId]: [...(prev[convId] ?? []), message],
    }));
  }, []);

  return (
    <InboxConversationsContext.Provider
      value={{
        conversations,
        setConversations,
        selectedId,
        setSelectedId,
        markAgentReplied,
        closeConversation,
        reopenConversation,
        transferConversation,
        getMessages,
        setMessages,
        appendMessage,
      }}
    >
      {children}
    </InboxConversationsContext.Provider>
  );
}

export function useInboxConversations() {
  return useContext(InboxConversationsContext);
}
