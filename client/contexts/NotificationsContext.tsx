'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { useAgents } from '@/contexts/AgentsContext';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const TENANT_ID = 1;

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

interface NotificationApi {
  id: number;
  type: string;
  message: string;
  description: string | null;
  from_agent_id: number | null;
  conversation_id: number | null;
  created_at: string;
  read: boolean;
}

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { getCurrentAgent } = useAgents();
  const [notifications, setNotifications] = useState<AgentNotification[]>([]);

  const currentAgentId = getCurrentAgent()?.id ?? null;

  const mapNotification = useCallback((n: NotificationApi): AgentNotification => {
    const rawType = n.type as NotificationType;
    const type: NotificationType = [
      'chat_transfer',
      'new_lead',
      'personal_message',
      'new_message',
      'assignment',
      'mention',
      'system',
    ].includes(rawType)
      ? rawType
      : 'system';
    return {
      id: String(n.id),
      type,
      message: n.message,
      description: n.description ?? undefined,
      createdAt: n.created_at,
      read: n.read,
      fromAgentId: n.from_agent_id != null ? String(n.from_agent_id) : undefined,
      conversationId: n.conversation_id ?? undefined,
    };
  }, []);

  const refreshNotifications = useCallback(async () => {
    if (!currentAgentId) {
      setNotifications([]);
      return;
    }
    try {
      const url = new URL(`${API_BASE}/api/notifications`);
      url.searchParams.set('tenant_id', String(TENANT_ID));
      url.searchParams.set('agent_id', String(Number(currentAgentId)));
      const res = await fetch(url.toString());
      if (!res.ok) return;
      const rows = (await res.json()) as NotificationApi[];
      setNotifications(rows.map(mapNotification));
    } catch {
      // ignore fetch errors
    }
  }, [currentAgentId, mapNotification]);

  useEffect(() => {
    void refreshNotifications();
  }, [refreshNotifications]);

  const getNotificationsForCurrentAgent = useCallback(() => {
    return notifications
      .filter((n) => n.toAgentId == null || n.toAgentId === currentAgentId)
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }, [notifications, currentAgentId]);

  const unreadCount = getNotificationsForCurrentAgent().filter((n) => !n.read).length;

  const addNotification = useCallback(
    (n: Omit<AgentNotification, 'id' | 'createdAt' | 'read'>) => {
      if (!n.toAgentId) return;
      void fetch(`${API_BASE}/api/notifications`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: TENANT_ID,
          agent_id: Number(n.toAgentId),
          type: n.type,
          message: n.message,
          description: n.description ?? null,
          from_agent_id: n.fromAgentId ? Number(n.fromAgentId) : null,
          conversation_id: n.conversationId ?? null,
        }),
      }).then(() => {
        void refreshNotifications();
      });
    },
    [refreshNotifications]
  );

  const markAsRead = useCallback(
    (id: string) => {
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
      void fetch(`${API_BASE}/api/notifications/${id}`, { method: 'PATCH' });
    },
    []
  );

  const markAllAsRead = useCallback(() => {
    if (!currentAgentId) return;
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    void fetch(`${API_BASE}/api/notifications/read-all?tenant_id=${TENANT_ID}&agent_id=${Number(currentAgentId)}`, {
      method: 'POST',
    });
  }, [currentAgentId]);

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
