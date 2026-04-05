'use client';

import { useEffect, useRef } from 'react';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';

export interface DmWsMessagePayload {
  id: number;
  conversation_id: number;
  sender_agent_id: number;
  content: string;
  created_at: string;
}

export type DmWsEvent = { type: 'NEW_DM_MESSAGE'; message: DmWsMessagePayload };

function wsUrlForDm(conversationId: number, tenantId: number, agentId: number, token: string): string {
  const wsBase = API_BASE.replace(/^http/i, (m) => (m.toLowerCase() === 'https' ? 'wss' : 'ws'));
  const q = new URLSearchParams({
    tenant_id: String(tenantId),
    token,
    agent_id: String(agentId),
  });
  return `${wsBase}/api/internal-dm/ws/conversation/${conversationId}?${q.toString()}`;
}

export type DmRealtimeOptions = {
  onOpen?: () => void;
  onClose?: () => void;
};

/**
 * WebSocket for internal DM: NEW_DM_MESSAGE fan-out (same pattern as team channel).
 */
export function useDmConversationRealtime(
  enabled: boolean,
  conversationId: number | null,
  tenantId: number,
  agentId: number | null,
  onEvent: (event: DmWsEvent) => void,
  options?: DmRealtimeOptions,
): void {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    if (!enabled || conversationId == null || conversationId < 1 || agentId == null || agentId < 1) {
      return;
    }
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('auth_token');
    if (!token) return;

    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      if (closed) return;
      try {
        ws = new WebSocket(wsUrlForDm(conversationId, tenantId, agentId, token));
      } catch {
        scheduleReconnect();
        return;
      }

      ws.onopen = () => {
        optionsRef.current?.onOpen?.();
      };

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string) as DmWsEvent;
          if (data && typeof data === 'object' && data.type === 'NEW_DM_MESSAGE' && data.message) {
            onEventRef.current(data);
          }
        } catch {
          // ignore
        }
      };

      ws.onclose = () => {
        optionsRef.current?.onClose?.();
        if (!closed) scheduleReconnect();
      };

      ws.onerror = () => {
        try {
          ws?.close();
        } catch {
          // ignore
        }
      };
    };

    const scheduleReconnect = () => {
      if (closed) return;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, 4000);
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      try {
        ws?.close();
      } catch {
        // ignore
      }
    };
  }, [enabled, conversationId, tenantId, agentId]);
}
