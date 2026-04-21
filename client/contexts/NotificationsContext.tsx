'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { useAgents } from '@/contexts/AgentsContext';
import { readAuthAgentId } from '@/lib/agent-session-storage';
import { parseBackendUtcDate } from '@/lib/tenant-time';
import { useAgentPortalRealtime } from '@/contexts/AgentPortalRealtimeContext';

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
  | 'system'
  | 'team_assigned'
  | 'team_removed'
  | 'team_changed'
  | 'system_welcome'
  | 'bot_new_chat'
  | 'broadcast';

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
  /** True until the first successful fetch for the current agent session (or no agent). */
  isNotificationsLoading: boolean;
  addNotification: (n: Omit<AgentNotification, 'id' | 'createdAt' | 'read'>) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  clearAllNotifications: () => void;
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

const DM_MSG_PREFIX = '__DM_MSG_JSON__';
const TEAM_MSG_PREFIX = '__TEAM_MSG_JSON__';

function summarizeStructuredMessage(raw: string | null | undefined): string | undefined {
  const v = (raw ?? '').trim();
  if (!v) return undefined;
  const decode = (jsonText: string): string | undefined => {
    try {
      const obj = JSON.parse(jsonText) as {
        text?: unknown;
        attachment?: { type?: unknown };
      };
      const text = typeof obj.text === 'string' ? obj.text.trim() : '';
      const attType = typeof obj.attachment?.type === 'string' ? obj.attachment.type : '';
      if (text) return text;
      if (attType === 'voice') return 'Voice message';
      if (attType === 'photo' || attType === 'image') return 'Image';
      if (attType === 'file') return 'Attachment';
      return 'Attachment';
    } catch {
      return undefined;
    }
  };
  if (v.startsWith(DM_MSG_PREFIX)) return decode(v.slice(DM_MSG_PREFIX.length));
  if (v.startsWith(TEAM_MSG_PREFIX)) return decode(v.slice(TEAM_MSG_PREFIX.length));
  if (v.startsWith('{') && v.includes('"attachment"')) return decode(v);
  return v;
}

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { getCurrentAgent } = useAgents();
  const [notifications, setNotifications] = useState<AgentNotification[]>([]);
  const [isNotificationsLoading, setIsNotificationsLoading] = useState(true);

  const currentAgentId = getCurrentAgent()?.id ?? readAuthAgentId();

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
      'team_assigned',
      'team_removed',
      'team_changed',
      'system_welcome',
      'bot_new_chat',
      'broadcast',
    ].includes(rawType)
      ? rawType
      : 'system';
    const sanitizedDescription = summarizeStructuredMessage(n.description ?? undefined);
    let sanitizedMessage = summarizeStructuredMessage(n.message) || n.message;
    if (
      type === 'personal_message' &&
      sanitizedDescription &&
      /direct message/i.test(sanitizedMessage) &&
      ['Voice message', 'Image', 'Attachment'].includes(sanitizedDescription)
    ) {
      sanitizedMessage = sanitizedMessage.replace(/sent you a direct message/i, `sent you a ${sanitizedDescription.toLowerCase()}`);
    }
    return {
      id: String(n.id),
      type,
      message: sanitizedMessage,
      description: sanitizedDescription,
      createdAt: n.created_at,
      read: n.read,
      fromAgentId: n.from_agent_id != null ? String(n.from_agent_id) : undefined,
      conversationId: n.conversation_id ?? undefined,
    };
  }, []);

  const { subscribe } = useAgentPortalRealtime();

  useEffect(() => {
    return subscribe((msg) => {
      if (msg.type !== 'notification' || !msg.notification || typeof msg.notification !== 'object') return;
      if (!currentAgentId) return;
      const raw = msg.notification as Record<string, unknown>;
      const idNum = Number(raw.id);
      if (!Number.isFinite(idNum)) return;
      const n: NotificationApi = {
        id: idNum,
        type: String(raw.type ?? 'system'),
        message: String(raw.message ?? ''),
        description: raw.description != null ? String(raw.description) : null,
        from_agent_id: raw.from_agent_id != null ? Number(raw.from_agent_id) : null,
        conversation_id: raw.conversation_id != null ? Number(raw.conversation_id) : null,
        created_at: typeof raw.created_at === 'string' ? raw.created_at : new Date().toISOString(),
        read: Boolean(raw.read),
      };
      setNotifications((prev) => {
        if (prev.some((x) => x.id === String(n.id))) return prev;
        return [mapNotification(n), ...prev];
      });
    });
  }, [subscribe, mapNotification, currentAgentId]);

  const refreshNotifications = useCallback(
    async (opts?: { trackInitialLoad?: boolean }) => {
      const track = opts?.trackInitialLoad === true;
      if (!currentAgentId) {
        setNotifications([]);
        if (track) setIsNotificationsLoading(false);
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
      } finally {
        if (track) setIsNotificationsLoading(false);
      }
    },
    [currentAgentId, mapNotification],
  );

  useEffect(() => {
    return subscribe((msg) => {
      if (msg.type !== 'portal_connected') return;
      // One-shot catch-up on websocket connect/reconnect.
      void refreshNotifications();
    });
  }, [subscribe, refreshNotifications]);

  useEffect(() => {
    setIsNotificationsLoading(true);
    void refreshNotifications({ trackInitialLoad: true });
  }, [refreshNotifications]);

  const getNotificationsForCurrentAgent = useCallback(() => {
    return notifications
      .filter((n) => n.toAgentId == null || n.toAgentId === currentAgentId)
      .sort((a, b) => (parseBackendUtcDate(b.createdAt) ?? new Date(b.createdAt)).getTime() - (parseBackendUtcDate(a.createdAt) ?? new Date(a.createdAt)).getTime());
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
        // Notification list updates via agent portal websocket; no polling refresh.
      });
    },
    []
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

  const clearAllNotifications = useCallback(() => {
    if (!currentAgentId) return;
    setNotifications([]);
    void fetch(`${API_BASE}/api/notifications?tenant_id=${TENANT_ID}&agent_id=${Number(currentAgentId)}`, {
      method: 'DELETE',
    }).catch(() => {
      // If delete fails, reload the list to keep UI consistent with server.
      void refreshNotifications();
    });
  }, [currentAgentId, refreshNotifications]);

  return (
    <NotificationsContext.Provider
      value={{
        notifications,
        unreadCount,
        isNotificationsLoading,
        addNotification,
        markAsRead,
        markAllAsRead,
        clearAllNotifications,
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
      isNotificationsLoading: false,
      addNotification: (_: Omit<AgentNotification, 'id' | 'createdAt' | 'read'>) => {},
      markAsRead: (_: string) => {},
      markAllAsRead: () => {},
      clearAllNotifications: () => {},
      getNotificationsForCurrentAgent: () => [] as AgentNotification[],
    };
  }
  return ctx;
}
