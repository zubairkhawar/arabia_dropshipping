'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { useAgents } from '@/contexts/AgentsContext';

const STORAGE_KEY = 'agent-notifications';

export type NotificationType =
  | 'chat_transfer'
  | 'new_lead'
  | 'personal_message'
  | 'new_message'
  | 'assignment'
  | 'mention'
  | 'system';

export interface AgentNotification {
  id: string;
  type: NotificationType;
  message: string;
  /** Optional description (e.g. transfer reason). */
  description?: string;
  fromAgentId?: string;
  fromAgentName?: string;
  /** If set, only this agent sees the notification. */
  toAgentId?: string;
  toAgentName?: string;
  conversationId?: number;
  conversationCustomerName?: string;
  createdAt: string;
  read: boolean;
}

interface NotificationsContextType {
  notifications: AgentNotification[];
  unreadCount: number;
  addNotification: (n: Omit<AgentNotification, 'id' | 'createdAt' | 'read'>) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  getNotificationsForCurrentAgent: () => AgentNotification[];
}

const NotificationsContext = createContext<NotificationsContextType | undefined>(undefined);

const SEED_KEY = 'agent-notifications-seeded';

function getSeedNotifications(): AgentNotification[] {
  const now = new Date();
  const ts = () => new Date(now.getTime() - Math.random() * 86400000 * 2).toISOString();
  return [
    {
      id: 'seed-new-lead',
      type: 'new_lead',
      message: 'New lead assigned to you',
      description: 'Ahmed Ali started a conversation and was assigned to your queue.',
      conversationCustomerName: 'Ahmed Ali',
      createdAt: ts(),
      read: false,
    },
    {
      id: 'seed-new-message',
      type: 'new_message',
      message: 'New message in conversation',
      description: 'Sarah Khan sent a new message in an active conversation.',
      conversationCustomerName: 'Sarah Khan',
      createdAt: ts(),
      read: false,
    },
    {
      id: 'seed-personal',
      type: 'personal_message',
      message: 'Personal message from Hamza',
      description: 'Hey, can you take the next transfer? I’m wrapping up with a customer.',
      fromAgentName: 'Hamza',
      createdAt: ts(),
      read: false,
    },
  ];
}

function loadFromStorage(): AgentNotification[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const seeded = localStorage.getItem(SEED_KEY);
    let list: AgentNotification[] = [];
    if (raw) {
      const parsed = JSON.parse(raw);
      list = Array.isArray(parsed) ? parsed : [];
    }
    if (!seeded && list.length === 0) {
      list = getSeedNotifications();
      localStorage.setItem(SEED_KEY, '1');
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
      } catch {
        // ignore
      }
    }
    return list;
  } catch {
    return [];
  }
}

function saveToStorage(list: AgentNotification[]) {
  try {
    if (typeof window !== 'undefined') localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    // ignore
  }
}

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { getCurrentAgent } = useAgents();
  const [notifications, setNotifications] = useState<AgentNotification[]>([]);

  useEffect(() => {
    setNotifications(loadFromStorage());
  }, []);

  const persist = useCallback((list: AgentNotification[]) => {
    setNotifications(list);
    saveToStorage(list);
  }, []);

  const currentAgentId = getCurrentAgent()?.id ?? null;

  const getNotificationsForCurrentAgent = useCallback(() => {
    return notifications
      .filter((n) => n.toAgentId == null || n.toAgentId === currentAgentId)
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }, [notifications, currentAgentId]);

  const unreadCount = getNotificationsForCurrentAgent().filter((n) => !n.read).length;

  const addNotification = useCallback(
    (n: Omit<AgentNotification, 'id' | 'createdAt' | 'read'>) => {
      const id = `notif-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const newOne: AgentNotification = {
        ...n,
        id,
        createdAt: new Date().toISOString(),
        read: false,
      };
      persist([...notifications, newOne]);
    },
    [notifications, persist]
  );

  const markAsRead = useCallback(
    (id: string) => {
      persist(
        notifications.map((n) => (n.id === id ? { ...n, read: true } : n))
      );
    },
    [notifications, persist]
  );

  const markAllAsRead = useCallback(() => {
    persist(notifications.map((n) => ({ ...n, read: true })));
  }, [notifications, persist]);

  return (
    <NotificationsContext.Provider
      value={{
        notifications,
        unreadCount,
        addNotification,
        markAsRead,
        markAllAsRead,
        getNotificationsForCurrentAgent,
      }}
    >
      {children}
    </NotificationsContext.Provider>
  );
}

export function useNotifications() {
  const ctx = useContext(NotificationsContext);
  if (ctx === undefined) {
    return {
      notifications: [] as AgentNotification[],
      unreadCount: 0,
      addNotification: (_: Omit<AgentNotification, 'id' | 'createdAt' | 'read'>) => {},
      markAsRead: (_: string) => {},
      markAllAsRead: () => {},
      getNotificationsForCurrentAgent: () => [] as AgentNotification[],
    };
  }
  return ctx;
}
